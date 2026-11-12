"""Orquestación de los bloques 8–21 del análisis completo."""

from __future__ import annotations

import json
import logging
import time
import warnings
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from .analysis_io import (
    OutputRegistry,
    cleanup_figure_temporaries,
    csv2,
    deduplicate_output_tree,
    sha256,
    table_pair,
)
from .analysis_utils import AnalysisSettings
from .cartography import MapContext
from .community import run_community_analysis
from .config import REGIONS
from .conservation import run_conservation_analysis
from .descriptive import run_descriptive_analysis
from .multiscale import run_multiscale_analysis
from .optional_analysis import run_functional_diversity
from .sex_analysis import run_sex_analysis
from .temporal import run_temporal_analysis
from .localization import (
    is_habitat_field,
    is_preserved_text_field,
    translate_habitat_value,
    translate_text,
)


LOGGER = logging.getLogger("hippodec_maps")


def _regional_data_control(assigned: gpd.GeoDataFrame) -> pd.DataFrame:
    """Documenta variables regionales vacías sin permitir medias vacías."""

    table = pd.DataFrame(assigned.drop(columns="geometry", errors="ignore"))
    if "Region_MITECO" not in table:
        table["Region_MITECO"] = "No data"
    observed_regions = [
        value
        for value in table["Region_MITECO"].dropna().astype(str).drop_duplicates().tolist()
        if value.strip()
    ]
    official_regions = [
        details["label"]
        for slug, details in REGIONS.items()
        if slug != "all"
    ]
    regions = official_regions + [
        value for value in observed_regions if value not in official_regions
    ]
    if not regions:
        regions = ["No data"]
    definitions = {
        "Depth": "Valores numéricos de profundidad no negativos.",
        "Habitat": "Valores de hábitat no vacíos.",
        "Temperature": "Valores numéricos de temperatura del agua.",
        "Abundance": "Valores numéricos no negativos de abundancia total.",
        "Sex": "Filas con al menos un recuento sexual registrado.",
    }
    def column(name: str) -> pd.Series:
        return table.get(name, pd.Series(pd.NA, index=table.index))

    rows: list[dict[str, Any]] = []
    for region in regions:
        subset = table.loc[table["Region_MITECO"].astype(str).eq(region)]
        checks = {
            "Depth": pd.to_numeric(column("Depth").loc[subset.index], errors="coerce"),
            "Habitat": column("Habitat").loc[subset.index],
            "Temperature": pd.to_numeric(column("Temperatura_gC").loc[subset.index], errors="coerce"),
            "Abundance": pd.to_numeric(column("N_total").loc[subset.index], errors="coerce"),
            "Sex": (
                pd.to_numeric(column("N hembra").loc[subset.index], errors="coerce").fillna(0)
                + pd.to_numeric(column("N macho").loc[subset.index], errors="coerce").fillna(0)
                + pd.to_numeric(column("N_indeterminado").loc[subset.index], errors="coerce").fillna(0)
            ),
        }
        for variable, values in checks.items():
            if variable == "Habitat":
                valid = values.notna() & values.astype("string").str.strip().ne("")
            elif variable == "Sex":
                valid = pd.to_numeric(values, errors="coerce").gt(0)
            else:
                valid = pd.to_numeric(values, errors="coerce").notna()
            n_valid = int(valid.sum())
            n_records = int(len(subset))
            status = "calculable" if n_valid else "not_calculable"
            explanation = (
                "Hay al menos un valor válido disponible."
                if n_valid
                else f"No existe un valor válido de {variable.lower()} en esta región; los resultados regionales que lo utilizan no son calculables."
            )
            rows.append(
                {
                    "Region_MITECO": region,
                    "variable": variable,
                    "n_records": n_records,
                    "n_valid": n_valid,
                    "completeness_pct": 100 * n_valid / max(n_records, 1),
                    "calculation_status": status,
                    "explanation": explanation,
                    "method": definitions[variable],
                    "region_assignment_basis": (
                        "Intersección directa con la demarcación MITECO; si no existe, se fija la región canónica con la malla oficial MITECO de referencia de 10 km, independiente de la resolución analítica."
                    ),
                }
            )
    return pd.DataFrame(rows)


def _run_with_runtime_warning_capture(
    label: str,
    function,
    *args,
    runtime_warning_rows: list[dict[str, Any]],
    **kwargs,
):
    started = time.perf_counter()
    LOGGER.info("    Inicio del subproceso: %s", label)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", RuntimeWarning)
        result = function(*args, **kwargs)
    for warning in caught:
        row = {
            "stage": label,
            "warning_type": warning.category.__name__,
            "message": str(warning.message),
            "source_file": str(warning.filename),
            "source_line": int(warning.lineno),
            "status": "captured_and_documented",
            "interpretation": (
                "Una agregación recibió valores no finitos; el resultado afectado se deja como NaN/no calculable."
                if "empty slice" in str(warning.message).casefold()
                else "Advertencia de ejecución capturada para su investigación."
            ),
            "action": "Consulte control_calidad_datos_regionales.csv y la ubicación de origen anterior; los grupos vacíos siguen marcados explícitamente como no calculables.",
        }
        runtime_warning_rows.append(row)
        LOGGER.warning(
            "%s en %s: %s", warning.category.__name__, label, warning.message
        )
    elapsed = time.perf_counter() - started
    LOGGER.info("    Subproceso completado: %s · %.1f s", label, elapsed)
    return result


def _presentation_json(value: Any, field_name: object | None = None) -> Any:
    if isinstance(value, str):
        return (
            translate_habitat_value(value)
            if is_habitat_field(field_name)
            else value
            if is_preserved_text_field(field_name)
            else translate_text(value)
        )
    if isinstance(value, dict):
        return {key: _presentation_json(item, key) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_presentation_json(item, field_name) for item in value]
    return value


def _settings(config: dict[str, Any]) -> AnalysisSettings:
    raw = config.get("analysis", {})
    periods: list[tuple[str, str, str]] = []
    for item in raw.get("temporal_periods", []) or []:
        if isinstance(item, dict) and all(
            key in item for key in ("label", "start", "end")
        ):
            periods.append((str(item["label"]), str(item["start"]), str(item["end"])))
    if len(periods) == 1:
        raise ValueError(
            "analysis.temporal_periods debe estar vacío para no comparar o contener al menos dos períodos comparativos."
        )
    permutations = int(raw.get("permutations", 999))
    if permutations < 9:
        raise ValueError("analysis.permutations debe ser como mínimo 9.")
    return AnalysisSettings(
        permutations=permutations,
        random_seed=int(raw.get("random_seed", 20260501)),
        bootstrap_iterations=int(raw.get("bootstrap_iterations", 1000)),
        min_records_cell=int(raw.get("min_records_cell", 2)),
        coastal_threshold_km=float(raw.get("coastal_threshold_km", 10.0)),
        similarity_threshold=float(raw.get("similarity_threshold", 0.55)),
        temporal_periods=tuple(periods),
    )



def _validate_priority_range(priority: pd.DataFrame) -> tuple[bool, dict[str, Any]]:
    """Validate the 0--100 priority domain without treating non-evaluable NA as failure.

    Ecological-priority cells may legitimately retain NA when the value is not estimable.
    Therefore range QA must be applied only to calculated values, while
    still requiring every cell explicitly marked as evaluable to have a finite score.
    """

    score_column = "ecological_priority_score"
    if score_column not in priority.columns:
        return False, {"missing_required_column": score_column}
    raw = priority[score_column]
    score = pd.to_numeric(raw, errors="coerce").replace([np.inf, -np.inf], np.nan)

    conversion_failures = raw.notna() & score.isna()
    finite = score.dropna()
    tolerance = 1e-9
    out_of_range = finite[(finite < -tolerance) | (finite > 100.0 + tolerance)]

    if "ecological_priority_evaluable" not in priority.columns:
        return False, {"missing_required_column": "ecological_priority_evaluable"}
    evaluable = (
        priority["ecological_priority_evaluable"]
        .astype("boolean")
        .fillna(False)
        .astype(bool)
    )

    evaluable_missing = evaluable & score.isna()
    condition = bool(
        not conversion_failures.any()
        and out_of_range.empty
        and not evaluable_missing.any()
    )
    detail = {
        "score_column": score_column,
        "calculated_values": int(score.notna().sum()),
        "non_evaluable_or_missing_values": int(score.isna().sum()),
        "evaluable_missing_values": int(evaluable_missing.sum()),
        "conversion_failures": int(conversion_failures.sum()),
        "out_of_range_values": int(len(out_of_range)),
        "minimum_calculated": float(finite.min()) if not finite.empty else None,
        "maximum_calculated": float(finite.max()) if not finite.empty else None,
    }
    return condition, detail

def _quality_control(
    assigned: gpd.GeoDataFrame,
    community: dict[str, Any],
    multiscale: dict[str, Any],
    temporal: dict[str, Any],
    conservation: dict[str, Any],
    settings: AnalysisSettings,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, condition: bool, detail: Any) -> None:
        checks.append(
            {"check": name, "status": "PASS" if condition else "FAIL", "detail": detail}
        )

    abundance_input = (
        pd.to_numeric(assigned["N_total"], errors="coerce")
        .fillna(0)
        .clip(lower=0)
        .sum()
    )
    abundance_matrix = community["abundance_matrix"].to_numpy(dtype=float).sum()
    check(
        "abundance_conservation_community_matrix",
        np.isclose(abundance_input, abundance_matrix),
        {"input": float(abundance_input), "matrix": float(abundance_matrix)},
    )
    check(
        "community_matrix_unique_ids",
        community["abundance_matrix"].index.is_unique,
        len(community["abundance_matrix"]),
    )
    check(
        "community_matrix_no_negative",
        bool((community["abundance_matrix"] >= 0).all().all()),
        "todos los valores >= 0",
    )
    presence_patterns = (
        community["abundance_matrix"].fillna(0).gt(0).astype("int8")
    )
    has_beta_variation = len(presence_patterns.drop_duplicates()) > 1
    expected_lcbd_sum = 1.0 if has_beta_variation else 0.0
    observed_lcbd_sum = float(community["lcbd"]["LCBD"].sum())
    check(
        "lcbd_sum",
        np.isclose(observed_lcbd_sum, expected_lcbd_sum),
        {
            "observed": observed_lcbd_sum,
            "expected": expected_lcbd_sum,
            "beta_variation_present": has_beta_variation,
        },
    )
    multiscale_statuses = {
        int(scale): str(result.get("status", "unknown"))
        for scale, result in multiscale["scale_results"].items()
    }
    check(
        "multiscale_scales",
        any(status == "estimable" for status in multiscale_statuses.values()),
        multiscale_statuses,
    )
    multiscale_spatial_qa = multiscale.get("spatial_qa", pd.DataFrame())
    check(
        "official_multiscale_hierarchy",
        bool(
            len(multiscale_spatial_qa)
            and not multiscale_spatial_qa["status"].eq("FAIL").any()
        ),
        multiscale_spatial_qa.to_dict("records"),
    )
    check(
        "temporal_periods",
        (not settings.temporal_periods and len(temporal["periods"]) == 1)
        or len(temporal["periods"]) >= 2,
        [period.label for period in temporal["periods"]],
    )
    temporal_quality = temporal.get("temporal_quality", pd.DataFrame())
    check(
        "temporal_mathematics",
        bool(
            len(temporal_quality)
            and temporal_quality["status"].eq("PASS").all()
        ),
        temporal_quality.to_dict("records"),
    )
    priority = conservation["priority_grid"]
    priority_range_ok, priority_range_detail = _validate_priority_range(priority)
    check(
        "priority_range",
        priority_range_ok,
        priority_range_detail,
    )
    check(
        "priority_classes_complete",
        bool(priority["ecological_priority_class"].notna().all()),
        priority["ecological_priority_class"].value_counts().to_dict(),
    )
    check(
        "assigned_observations_retained",
        len(assigned) > 0,
        {"assigned": int(len(assigned)), "records_used": int(len(assigned))},
    )
    check(
        "very_high_ecological_rule",
        bool(
            priority.loc[
                priority["ecological_priority_class"].eq("Muy alta"), "strong_ecological_criterion"
            ].all()
        ),
        "all Muy alta cells meet strong criterion",
    )
    selected = conservation["selected_cells"]
    check(
        "selected_cells_are_high",
        bool(selected["ecological_priority_class"].isin(["Alta", "Muy alta"]).all()),
        len(selected),
    )
    if not selected.empty:
        check(
            "selected_cells_have_zone",
            bool(selected["zone_id"].notna().all()),
            selected["zone_id"].nunique(),
        )
    conservation_spatial_qa = conservation.get("spatial_qa", pd.DataFrame())
    check(
        "conservation_geometry",
        bool(
            len(conservation_spatial_qa)
            and conservation_spatial_qa["status"].eq("PASS").all()
        ),
        conservation_spatial_qa.to_dict("records"),
    )
    check("permutation_seed_fixed", settings.random_seed > 0, settings.random_seed)
    failed = [row for row in checks if row["status"] == "FAIL"]
    if failed:
        raise AssertionError(
            "Han fallado los controles analíticos: "
            + ", ".join(row["check"] for row in failed)
        )
    return {"status": "passed", "checks": checks}


def run_full_analysis(
    run_root: Path,
    directories: dict[str, Path],
    config: dict[str, Any],
    paths: dict[str, Path | str | None],
    assigned: gpd.GeoDataFrame,
    occupied_cells: gpd.GeoDataFrame,
    cell_metrics: pd.DataFrame,
    cartographic_context: MapContext,
    html_context: dict[str, object],
    selected_grid_km: int,
    official_marine_cells: gpd.GeoDataFrame | None = None,
    official_multiscale_grids: dict[int, gpd.GeoDataFrame] | None = None,
    marine_mask: gpd.GeoDataFrame | None = None,
) -> dict[str, Any]:
    settings = _settings(config)
    registry = OutputRegistry(run_root)
    runtime_warning_rows: list[dict[str, Any]] = []
    LOGGER.info(
        "Iniciando el análisis completo (bloques 8–21); %d permutaciones.",
        settings.permutations,
    )

    LOGGER.info("[1/8] Análisis descriptivo, hábitat y profundidad")
    descriptive = _run_with_runtime_warning_capture(
        "descriptive",
        run_descriptive_analysis,
        assigned,
        occupied_cells,
        directories,
        Path(paths["gshhg"]) if paths.get("gshhg") else None,
        settings,
        registry,
        runtime_warning_rows=runtime_warning_rows,
    )
    LOGGER.info("[2/8] Comunidad, diversidad beta, LCBD y biogeografía")
    community = _run_with_runtime_warning_capture(
        "community",
        run_community_analysis,
        assigned,
        occupied_cells,
        cell_metrics,
        directories,
        settings,
        registry,
        cartographic_context,
        runtime_warning_rows=runtime_warning_rows,
    )
    LOGGER.info("[3/8] Diversidad funcional opcional")
    functional = _run_with_runtime_warning_capture(
        "functional_diversity",
        run_functional_diversity,
        assigned,
        Path(paths["traits"]) if paths.get("traits") else None,
        directories,
        registry,
        runtime_warning_rows=runtime_warning_rows,
    )
    LOGGER.info("[4/8] Comunidades y hotspots multiescala")
    multiscale = _run_with_runtime_warning_capture(
        "multiscale",
        run_multiscale_analysis,
        assigned,
        directories,
        settings,
        registry,
        cartographic_context,
        selected_grid_km,
        official_marine_cells if official_marine_cells is not None else occupied_cells,
        community,
        official_multiscale_grids=official_multiscale_grids,
        nearest_tolerance_factor=float(config["spatial"].get("nearest_tolerance_factor", 1.0)),
        runtime_warning_rows=runtime_warning_rows,
    )
    LOGGER.info("[5/8] Composición sexual")
    sex = _run_with_runtime_warning_capture(
        "sex",
        run_sex_analysis,
        assigned,
        occupied_cells,
        directories,
        registry,
        selected_grid_km,
        runtime_warning_rows=runtime_warning_rows,
    )
    LOGGER.info("[6/8] Análisis temporal avanzado")
    temporal = _run_with_runtime_warning_capture(
        "temporal",
        run_temporal_analysis,
        assigned,
        official_marine_cells if official_marine_cells is not None else occupied_cells,
        directories,
        settings,
        registry,
        cartographic_context,
        selected_grid_km,
        runtime_warning_rows=runtime_warning_rows,
    )
    LOGGER.info("[7/8] Priorización y zonas de conservación")
    conservation = _run_with_runtime_warning_capture(
        "conservation",
        run_conservation_analysis,
        multiscale,
        temporal,
        Path(paths["protected_areas"]) if paths.get("protected_areas") else None,
        Path(paths["demarcations"]) if paths.get("demarcations") else None,
        Path(paths["logo"]) if paths.get("logo") else None,
        directories,
        registry,
        cartographic_context,
        html_context,
        selected_grid_km,
        assigned,
        marine_mask,
        Path(paths["gshhg"]) if paths.get("gshhg") else None,
        runtime_warning_rows=runtime_warning_rows,
    )
    cleanup_figure_temporaries(run_root)

    # Diagnósticos explícitos de correspondencia entre hotspots, señal temporal
    # y malla de prioridad (nombres conservados del bloque 21 de R).
    master_ids = multiscale["master_hotspots"]["master_id"].astype(str)
    priority_ids = conservation["priority_grid"]["master_id"].astype(str)
    coverage = pd.DataFrame([{
        "selected_grid_km": selected_grid_km,
        "master_hotspot_cells": master_ids.nunique(),
        "priority_cells": priority_ids.nunique(),
        "matched_cells": priority_ids.isin(set(master_ids)).sum(),
        "coverage_pct": 100 * priority_ids.isin(set(master_ids)).mean() if len(priority_ids) else np.nan,
    }])
    missing_priority = pd.DataFrame({
        "master_id": priority_ids[~priority_ids.isin(set(master_ids))].drop_duplicates()
    })
    for frame, name, description in (
        (coverage, "Control_21_Cobertura_Malla_Prioridad_Hotspot.csv", "Cobertura de la prioridad de hotspots"),
        (missing_priority, "Control_21_Celdas_Prioridad_Sin_Hotspot_Maestro.csv", "Celdas prioritarias sin hotspot maestro"),
    ):
        path = csv2(frame, directories["07_debug"] / name)
        registry.add(path, "21", description)

    regional_control = _regional_data_control(assigned)
    regional_control_path = csv2(
        regional_control,
        directories["07_debug"] / "control_calidad_datos_regionales.csv",
    )
    registry.add(
        regional_control_path,
        "QA",
        "Control regional de completitud y calculabilidad de variables",
    )

    if runtime_warning_rows:
        runtime_control = pd.DataFrame(runtime_warning_rows)
    else:
        runtime_control = pd.DataFrame(
            [
                {
                    "stage": "complete_analysis",
                    "warning_type": "RuntimeWarning",
                    "message": "No se emitió ninguna RuntimeWarning durante el análisis completo.",
                    "source_file": "",
                    "source_line": "",
                    "status": "none_emitted",
                    "interpretation": "No se produjo ninguna advertencia de segmento vacío; los grupos regionales vacíos se comprobaron explícitamente.",
                    "action": "Las variables regionales vacías siguen comprobándose explícitamente en control_calidad_datos_regionales.csv.",
                }
            ]
        )
    runtime_control_path = csv2(
        runtime_control,
        directories["07_debug"] / "control_advertencias_ejecucion.csv",
    )
    registry.add(runtime_control_path, "QA", "Investigación y gestión de RuntimeWarning")

    duplicates = deduplicate_output_tree(
        run_root,
        registry,
        include_dirs=(
            "01_parametros",
            "02_intermedios",
            "04_tablas",
            "05_figuras",
            "06_modelos",
            "07_control_calidad",
            "09_zonas_prioritarias_conservacion",
        ),
    )
    duplicate_control = pd.DataFrame(duplicates)
    if duplicate_control.empty:
        duplicate_control = pd.DataFrame(
            [
                {
                    "status": "No se encontraron duplicados",
                    "removed_file": "",
                    "canonical_file": "",
                    "content_signature": "",
                    "reason": "Cada salida registrada tiene una firma de contenido única.",
                }
            ]
        )
    duplicate_control_path = csv2(
        duplicate_control,
        directories["07_debug"] / "control_salidas_duplicadas.csv",
    )
    registry.add(duplicate_control_path, "QA", "Control de salidas duplicadas")

    # Manifiestos tabulares equivalentes a los productos finales del bloque 20.
    manifest_frame = pd.DataFrame(registry.records)
    main_outputs = manifest_frame[~manifest_frame.get("status", "written").eq("skipped")].copy()
    internal_outputs = manifest_frame[manifest_frame.get("status", "written").eq("skipped")].copy()
    for name, frame in (
        ("MANIFIESTO_Bloque20_Resultados_Avanzados", main_outputs),
        ("MANIFIESTO_Salidas_Internas_No_Principales", internal_outputs),
    ):
        csv_path, xlsx_path = table_pair(frame, directories["04_tablas"] / "manifiestos" / name)
        registry.add(csv_path, "20", f"Manifiesto de salidas: {name}")
        registry.add(xlsx_path, "20", f"Manifiesto de salidas: {name}")

    quality = _quality_control(
        assigned, community, multiscale, temporal, conservation, settings
    )
    qa_path = directories["07_debug"] / "control_calidad_analisis_completo.json"
    qa_path.write_text(
        json.dumps(_presentation_json(quality), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    registry.add(qa_path, "QA", "Comprobaciones de integridad del análisis completo")

    # Se repite el control de duplicados en el último punto posible, después de
    # ensamblar todos los productos y manifiestos, antes de escribir el manifiesto JSON.
    late_duplicates = deduplicate_output_tree(
        run_root,
        registry,
        include_dirs=(
            "01_parametros",
            "02_intermedios",
            "04_tablas",
            "05_figuras",
            "06_modelos",
            "07_control_calidad",
            "09_zonas_prioritarias_conservacion",
        ),
    )
    if late_duplicates:
        by_key = {
            (
                row.get("removed_file", ""),
                row.get("canonical_file", ""),
                row.get("content_signature", ""),
            ): row
            for row in [*duplicates, *late_duplicates]
        }
        duplicates = list(by_key.values())
        duplicate_control_path = csv2(
            pd.DataFrame(duplicates), duplicate_control_path
        )
        duplicate_relative = str(
            duplicate_control_path.resolve().relative_to(run_root.resolve())
        ).replace("\\", "/")
        for record in registry.records:
            if record.get("file") == duplicate_relative:
                record["bytes"] = duplicate_control_path.stat().st_size
                record["sha256"] = sha256(duplicate_control_path)
                break
    LOGGER.info("[8/8] Síntesis e informe técnico integral")
    from .technical_report import build_integrated_technical_report
    technical_report_path = _run_with_runtime_warning_capture(
        "technical_report",
        build_integrated_technical_report,
        run_root=run_root,
        output_dir=directories["10_informe_tecnico"],
        context=html_context,
        assigned=assigned,
        occupied_cells=occupied_cells,
        cell_metrics=cell_metrics,
        selected_grid_km=selected_grid_km,
        settings=settings,
        descriptive=descriptive,
        community=community,
        functional=functional,
        multiscale=multiscale,
        sex=sex,
        temporal=temporal,
        conservation=conservation,
        quality_control_path=qa_path,
        runtime_warning_rows=runtime_warning_rows,
    )
    registry.add(technical_report_path, "22", "Informe técnico integral de la ejecución")

    manifest_path = registry.write(
        directories["07_debug"] / "manifiesto_salidas_analisis.json",
        extra={
            "analysis_settings": {
                "permutations": settings.permutations,
                "random_seed": settings.random_seed,
                "bootstrap_iterations": settings.bootstrap_iterations,
                "min_records_cell": settings.min_records_cell,
                "coastal_threshold_km": settings.coastal_threshold_km,
            },
            "optional_blocks": {
                "functional_diversity": bool(functional.get("available")),
                "sexual_analysis": bool(sex.get("available")),
                "protected_areas": bool(conservation.get("protected_areas_loaded")),
            },
            "runtime_warning_control": str(runtime_control_path),
            "regional_data_quality_control": str(regional_control_path),
            "duplicate_output_control": str(duplicate_control_path),
            "duplicates_removed": len(duplicates),
            "region_assignment_method": "Primero se utiliza la intersección directa punto-demarcación; cuando falta, la región canónica se fija con la malla oficial MITECO de referencia de 10 km, independientemente de la resolución analítica.",
        },
    )
    LOGGER.info("Análisis completo finalizado. Control de calidad: SUPERADO")
    return {
        "descriptive": descriptive,
        "community": community,
        "functional": functional,
        "multiscale": multiscale,
        "sex": sex,
        "temporal": temporal,
        "conservation": conservation,
        "qa": qa_path,
        "manifest": manifest_path,
        "priority_map": conservation["interactive_map"],
        "priority_report": conservation["report"],
        "technical_report": technical_report_path,
        "regional_data_quality_control": regional_control_path,
        "runtime_warning_control": runtime_control_path,
        "duplicate_output_control": duplicate_control_path,
        "duplicates_removed": duplicates,
    }
