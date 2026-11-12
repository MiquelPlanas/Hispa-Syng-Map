"""Orchestration of Hippo-DEC maps and analytical blocks 8–21."""

from __future__ import annotations

import json
import logging
import platform
import re
import shutil
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml

from .cartography import feature_collection, load_map_context
from .config import RunParameters, ascii_slug
from .data import add_species_authorities, filter_observations
from .grids import load_grids, prepare_grid_root, prepare_gshhg_root
from .output_policy import copy_public_registration
from .maps import (
    build_map1_observations,
    cells_feature_collection,
    common_context,
    logo_data_uri,
    render_map1,
    render_map2,
    render_map3,
    render_viewer,
    rewrite_language_switch,
)
from .metrics import calculate_metrics
from .localization import (
    translate_frame,
    translate_geodataframe,
    translate_json_presentation,
    translate_text,
)
from .regions import (
    assign_observation_regions,
    boundaries_for_map,
    filter_region,
    load_demarcations,
    observations_to_points,
)
from .sampling import sampling_event_summary
from .spatial import (
    assign_points_to_grid,
    assign_regions_from_reference_grid,
    build_assignment_spatial_audit,
    clip_occupied_cells_with_land,
    prepare_marine_grid_areas,
    region_assignment_control,
    write_assignment_qc_map,
)


LOGGER = logging.getLogger("hippodec_maps")
_RUN_STARTED_MONOTONIC = time.perf_counter()


def _prepare_official_multiscale_grids(
    grid_root: Path,
    selected_grid: gpd.GeoDataFrame,
    selected_grid_km: int,
    selected_region: str,
    points: gpd.GeoDataFrame,
    config: dict[str, Any],
    gshhg_path: Path,
    cache_dir: Path,
    marine_regions: gpd.GeoDataFrame,
) -> tuple[dict[int, gpd.GeoDataFrame], pd.DataFrame]:
    """Prepare official 1/5/10 km MITECO grids without reloading the selected grid."""

    grids: dict[int, gpd.GeoDataFrame] = {int(selected_grid_km): selected_grid.copy()}
    rows: list[dict[str, Any]] = [
        {
            "scale_km": int(selected_grid_km),
            "status": "available_reused_selected_grid",
            "n_cells": int(len(selected_grid)),
            "source_files": int(selected_grid.get("source_file", pd.Series(dtype="object")).nunique()),
            "marine_area_cache_status": "already_prepared",
            "marine_area_cache_cells_reused": np.nan,
            "marine_area_cache_cells_computed": np.nan,
            "detail": "The selected grid was already validated during cartographic preparation.",
        }
    ]
    target_crs = int(config["spatial"]["target_crs"])
    bbox_factor = float(config["spatial"].get("grid_bbox_buffer_factor", 1.25))
    for scale_km in (1, 5, 10):
        if scale_km == int(selected_grid_km):
            continue
        try:
            LOGGER.info("  [3.4] Preparing official %d km MITECO grid for multiscale analysis", scale_km)
            scale_started = time.perf_counter()
            scale_grid, inventory = load_grids(
                grid_root,
                scale_km,
                selected_region,
                points,
                target_crs=target_crs,
                bbox_buffer_factor=bbox_factor,
            )
            LOGGER.info('  [3.4 · %dkm] Read and preparation: %.2f s; %d cells. Checking marine areas.', scale_km, time.perf_counter() - scale_started, len(scale_grid))
            area_started = time.perf_counter()
            scale_grid, area_qa = prepare_marine_grid_areas(
                scale_grid,
                gshhg_path,
                cache_dir=cache_dir,
                resolution_km=scale_km,
                progress_callback=lambda message, scale=scale_km: LOGGER.info(
                    "  [3.4 · %dkm] %s", scale, message
                ),
                marine_regions=marine_regions,
            )
            LOGGER.info('  [3.4 · %dkm] Areas: %.2f s; full scale: %.2f s.', scale_km, time.perf_counter() - area_started, time.perf_counter() - scale_started)
            grids[scale_km] = scale_grid
            rows.append(
                {
                    "scale_km": scale_km,
                    "status": "available",
                    "n_cells": int(len(scale_grid)),
                    "source_files": int(len(inventory)),
                    "marine_area_cache_status": area_qa.get("marine_area_cache_status", "unknown"),
                    "marine_area_cache_cells_reused": int(area_qa.get("marine_area_cache_cells_reused", 0)),
                    "marine_area_cache_cells_computed": int(area_qa.get("marine_area_cache_cells_computed", 0)),
                    "detail": "Official grid loaded around records and marine area validated with GSHHS.",
                }
            )
        except Exception as exc:
            LOGGER.warning(
                "The official %d km MITECO grid is unavailable for multiscale analysis: %s",
                scale_km,
                exc,
            )
            rows.append(
                {
                    "scale_km": scale_km,
                    "status": "not_available",
                    "n_cells": 0,
                    "source_files": 0,
                    "marine_area_cache_status": "not_available",
                    "marine_area_cache_cells_reused": 0,
                    "marine_area_cache_cells_computed": 0,
                    "detail": str(exc),
                }
            )
    return grids, pd.DataFrame(rows).sort_values("scale_km").reset_index(drop=True)


class _ElapsedFormatter(logging.Formatter):
    """Prefix console messages with the elapsed time of the current run."""

    def format(self, record: logging.LogRecord) -> str:
        elapsed = max(0, int(time.perf_counter() - _RUN_STARTED_MONOTONIC))
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"[{hours:02d}:{minutes:02d}:{seconds:02d}] {super().format(record)}"


class _EnglishLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = translate_text(record.msg)
        return True


def _species_tag(selected: tuple[str, ...], available: list[str]) -> str:
    if len(selected) == len(available):
        return "allspp"
    if len(selected) == 1:
        parts = selected[0].split()
        return ascii_slug(
            (parts[0][0] if parts else "s") + (parts[1] if len(parts) > 1 else "p")
        )
    return f"{len(selected)}spp"


def _build_language_switch(
    run_root: Path,
    params: RunParameters,
) -> dict[str, object]:
    """Describe the matching HTML pages in the paired language run."""

    language = str(params.language_code or "").upper()
    if not params.execution_id or language not in {"ES", "EN"}:
        return {"enabled": False}
    results_root = run_root.parent
    es_root = results_root / f"ejecucion_{params.execution_id}_ESP"
    en_root = results_root / f"run_{params.execution_id}_EN"
    names = {
        "ES": {
            "map1": f"Mapa1_Observaciones_{params.grid_km}km_{params.year_tag}_{params.region}.html",
            "map2": f"Mapa2_Densidad_{params.grid_km}km_{params.year_tag}_{params.region}.html",
            "map3": f"Mapa3_Variables_{params.grid_km}km_{params.year_tag}_{params.region}.html",
            "priority": f"Mapa_Interactivo_Zonas_Prioritarias_Conservacion_{params.grid_km}km.html",
            "viewer": f"Visor_Hippo_DEC_{params.grid_km}km_{params.year_tag}_{params.region}.html",
        },
        "EN": {
            "map1": f"Map1_Observations_{params.grid_km}km_{params.year_tag}_{params.region}.html",
            "map2": f"Map2_Density_{params.grid_km}km_{params.year_tag}_{params.region}.html",
            "map3": f"Map3_Variables_{params.grid_km}km_{params.year_tag}_{params.region}.html",
            "priority": f"Interactive_Priority_Conservation_Areas_Map_{params.grid_km}km.html",
            "viewer": f"Hippo_DEC_Viewer_{params.grid_km}km_{params.year_tag}_{params.region}.html",
        },
    }
    folders = {
        "ES": {
            "map1": "03_mapas",
            "map2": "03_mapas",
            "map3": "03_mapas",
            "priority": "09_zonas_prioritarias_conservacion/mapas",
            "viewer": "08_visores",
        },
        "EN": {
            "map1": "03_maps",
            "map2": "03_maps",
            "map3": "03_maps",
            "priority": "09_priority_conservation_areas/maps",
            "viewer": "08_viewers",
        },
    }
    roots = {"ES": es_root, "EN": en_root}
    targets = {
        page: {
            code: roots[code] / folders[code][page] / names[code][page]
            for code in ("ES", "EN")
        }
        for page in names["ES"]
    }
    return {
        "enabled": True,
        "current": language,
        "labels": {"ES": "Español", "EN": "English"},
        "control_label": "Language / Idioma",
        "run_roots": roots,
        "names": names,
        "targets": targets,
    }


def _create_run_dirs(
    results_root: Path,
    params: RunParameters,
    available_species: list[str],
    forced_root: Path | None = None,
) -> tuple[Path, dict[str, Path]]:
    if forced_root is not None:
        root = Path(forced_root).expanduser().resolve()
        if root.exists():
            raise FileExistsError(f"The run folder already exists: {root}")
    else:
        now = datetime.now()
        if params.execution_id:
            run_id = "_".join(
                [
                    "run",
                    params.execution_id,
                    params.language_code or "EN",
                ]
            )
        else:
            run_id = "_".join(
                [
                    "run",
                    now.strftime("%Y-%m-%d"),
                    now.strftime("%H%M%S"),
                    params.year_tag,
                    f"{params.grid_km}km",
                    params.region,
                    _species_tag(params.species_raw, available_species),
                ]
            )
        root = results_root / run_id
        suffix = 2
        while root.exists():
            root = results_root / f"{run_id}_{suffix}"
            suffix += 1
    names = {
        "00_logs": "00_logs",
        "01_parametros": "01_parameters",
        "02_intermedios": "02_intermediate",
        "03_mapas": "03_maps",
        "04_tablas": "04_tables",
        "05_figuras": "05_figures",
        "06_modelos": "06_models",
        "07_debug": "07_quality_control",
        "08_visores": "08_viewers",
        "09_zonas_prioritarias_conservacion": "09_priority_conservation_areas",
        "10_informe_tecnico": "10_technical_report",
    }
    directories = {key: root / value for key, value in names.items()}
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=False)
    return root, directories


def _setup_logging(path: Path) -> None:
    global _RUN_STARTED_MONOTONIC
    _RUN_STARTED_MONOTONIC = time.perf_counter()
    LOGGER.setLevel(logging.INFO)
    LOGGER.handlers.clear()
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.addFilter(_EnglishLogFilter())
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(_ElapsedFormatter("%(message)s"))
    console.addFilter(_EnglishLogFilter())
    LOGGER.addHandler(file_handler)
    LOGGER.addHandler(console)


def _csv2(data: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    translate_frame(data).to_csv(
        path, sep=";", decimal=",", index=False, encoding="utf-8-sig", na_rep=""
    )


def _plain_table(frame: pd.DataFrame | gpd.GeoDataFrame) -> pd.DataFrame:
    return pd.DataFrame(frame.drop(columns="geometry", errors="ignore"))


def _presentation_json(value: Any, field_name: object | None = None) -> Any:
    """Present QA labels while retaining the exact recorded references."""

    return translate_json_presentation(value, field_name)


def _validate_html(
    path: Path,
    required: list[str],
    forbidden: list[str] | None = None,
    *,
    scoped_fields: tuple[str, ...] | None = None,
    scoped_forbidden: list[str] | None = None,
) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    missing = [token for token in required if token not in text]
    if missing:
        raise AssertionError(f"HTML file {path.name} does not contain: {', '.join(missing)}")
    field_values: list[str] = []
    if scoped_fields:
        for field in scoped_fields:
            field_values.extend(
                re.findall(
                    rf'"{re.escape(field)}"\s*:\s*"((?:\\.|[^"\\])*)"',
                    text,
                )
            )
        # The validator intentionally ignores arbitrary free text such as the
        # source Comments field.  Habitat translations are checked only where
        # the generated HTML serialises a habitat-valued field.
        searched_text = "\n".join(field_values)
    else:
        searched_text = ""
    # General dependency checks scan the complete HTML document.  Habitat
    # checks are deliberately field-scoped so source-faithful free text (for
    # example an observation comment) is not rewritten or misclassified.
    unexpected = [token for token in (forbidden or []) if token in text]
    unexpected.extend(
        token for token in (scoped_forbidden or []) if token in searched_text
    )
    if unexpected:
        raise AssertionError(
            f"HTML file {path.name} contains untranslated habitat values in generated fields: {', '.join(unexpected)}"
        )
    return {
        "file": str(path),
        "bytes": path.stat().st_size,
        "required_tokens_ok": True,
        "forbidden_tokens_absent": True,
        "field_scoped_habitat_check": bool(scoped_fields),
        "habitat_fields_checked": list(scoped_fields or ()),
        "habitat_field_values_checked": len(field_values),
        "source_free_text_ignored": bool(scoped_fields),
        "general_forbidden_tokens_checked": list(forbidden or ()),
        "scoped_forbidden_tokens_checked": list(scoped_forbidden or ()),
    }


def run_pipeline(
    project_root: Path,
    config: dict[str, Any],
    paths: dict[str, Path | str | None],
    raw_data: pd.DataFrame,
    input_summary: dict[str, Any],
    params: RunParameters,
    *,
    forced_run_root: Path | None = None,
    resource_root: Path | None = None,
) -> dict[str, Path]:
    run_root, directories = _create_run_dirs(
        Path(paths["results"]),
        params,
        input_summary["available_species"],
        forced_root=forced_run_root,
    )
    resource_root = Path(resource_root or project_root).expanduser().resolve()
    _setup_logging(directories["00_logs"] / "run.log")
    LOGGER.info("Hispa-Syng v1.0 (Hippo-DEC project) — run %s", run_root.name)
    LOGGER.info("Input: %s", paths["excel"])
    if "Id" in raw_data.columns:
        LOGGER.info(
            "Id field: retained as metadata; it is not used as an analytical variable, key, or deduplication criterion."
        )
    LOGGER.info(
        "Protected areas: %s",
        paths.get("protected_areas") or "not available (optional block)",
    )
    LOGGER.info(
        "Functional traits: %s",
        paths.get("traits") or "not available (optional block)",
    )
    LOGGER.info(
        "Parameters: %s–%s | %s km | %s | %s species",
        params.year_min,
        params.year_max,
        params.grid_km,
        params.region_label,
        len(params.species_raw),
    )
    LOGGER.info("[Preparation · 1/8] Input and parameter audit")
    input_audit = input_summary.get("input_audit", {})
    if input_audit:
        (directories["07_debug"] / "input_audit.json").write_text(
            json.dumps(input_audit, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        field_rows = input_audit.get("fields", [])
        if field_rows:
            _csv2(
                pd.DataFrame(field_rows),
                directories["07_debug"] / "excel_field_audit.csv",
            )
        for warning in input_audit.get("warnings", []):
            LOGGER.warning("Input audit: %s", warning)

    LOGGER.info("[Preparation · 2/8] Filters and preliminary regional assignment")
    filtered, discarded, filter_counts = filter_observations(raw_data, params)
    if not discarded.empty:
        _csv2(
            discarded, directories["07_debug"] / "discarded_invalid_coordinates.csv"
        )
    LOGGER.info(
        "Valid records after species, period, and coordinate filters: %d", len(filtered)
    )

    regions = load_demarcations(
        Path(paths["demarcations"]), int(config["spatial"]["target_crs"])
    )
    points = observations_to_points(filtered, int(config["spatial"]["target_crs"]))
    points = assign_observation_regions(points, regions)
    direct_region_values = points["Region_slug"].astype("string").str.strip().str.casefold()
    direct_region_missing = points["Region_slug"].isna() | direct_region_values.isin(
        {"", "nan", "none", "no data", "sin datos", "sin_datos", "no region"}
    )
    points["Region_slug_scope"] = points["Region_slug"]
    points["Region_MITECO_scope"] = points["Region_MITECO"]
    points["region_scope_method"] = np.where(
        direct_region_missing, "unresolved", "direct_demarcation_intersection"
    )
    points["reference_grid_id"] = pd.NA
    points["reference_region_distance_m"] = np.nan

    LOGGER.info("[Preparation · 3/8] MITECO–GSHHS cartographic preparation")
    LOGGER.info("  [3.1] Preparing and locating MITECO grids")
    grid_root = prepare_grid_root(Path(paths["grids"]), project_root / ".cache")

    # Regional selection must be independent of the analytical resolution.
    # Observations without a direct subdivision intersection receive a
    # canonical region from the official 10-km MITECO grid. The 1/5/10-km grid
    # selected by the user is then used only for analytical cell assignment
    # and for metrics/density calculations.
    reference_assignment = pd.DataFrame()
    if direct_region_missing.any():
        LOGGER.info(
            "  [3.1] Canonical regional assignment for %d records without a direct subdivision (10-km MITECO reference)",
            int(direct_region_missing.sum()),
        )
        reference_points = points.loc[direct_region_missing].copy()
        reference_grid, _reference_inventory = load_grids(
            grid_root,
            10,
            "all",
            reference_points,
            target_crs=int(config["spatial"]["target_crs"]),
            bbox_buffer_factor=float(
                config["spatial"].get("grid_bbox_buffer_factor", 1.25)
            ),
        )
        reference_assignment = assign_regions_from_reference_grid(
            reference_points,
            reference_grid,
            10_000.0,
        )
        if not reference_assignment.empty:
            ref = reference_assignment.set_index("obs_id")
            obs_ids = points["obs_id"]
            for target, source in (
                ("Region_slug_scope", "Region_slug_reference"),
                ("Region_MITECO_scope", "Region_MITECO_reference"),
                ("region_scope_method", "reference_region_method"),
                ("reference_grid_id", "reference_grid_id"),
                ("reference_region_distance_m", "reference_region_distance_m"),
            ):
                mapped = obs_ids.map(ref[source])
                mask = direct_region_missing & mapped.notna()
                points.loc[mask, target] = mapped.loc[mask]

    scope_region_values = (
        points["Region_slug_scope"].astype("string").str.strip().str.casefold()
    )
    scope_region_missing = points["Region_slug_scope"].isna() | scope_region_values.isin(
        {"", "nan", "none", "no data", "sin datos", "sin_datos", "no region", "<na>"}
    )
    if params.region == "all":
        candidate_points = points.copy()
    else:
        candidate_points = points.loc[
            scope_region_values.eq(params.region.casefold())
        ].copy()
    filter_counts["rows_before_region"] = int(len(candidate_points))
    filter_counts["rows_direct_region_missing"] = int(direct_region_missing.sum())
    filter_counts["rows_region_reference_10km"] = int(
        points["region_scope_method"].astype("string").str.startswith("reference_grid_10km").sum()
    )
    filter_counts["rows_region_scope_unresolved"] = int(scope_region_missing.sum())
    filter_counts["rows_selected_region_scope"] = int(len(candidate_points))

    regional_audit_columns = [
        "obs_id",
        "Region_slug",
        "Region_MITECO",
        "Region_slug_scope",
        "Region_MITECO_scope",
        "region_scope_method",
        "reference_grid_id",
        "reference_region_distance_m",
    ]
    _csv2(
        _plain_table(points[regional_audit_columns].copy()),
        directories["07_debug"] / "regional_assignment_audit.csv",
    )
    LOGGER.info(
        "  [3.1] Canonical regional scope: %d records; 10-km reference applied to %d; without canonical region: %d",
        len(candidate_points),
        filter_counts["rows_region_reference_10km"],
        filter_counts["rows_region_scope_unresolved"],
    )
    LOGGER.info("  [3.2] Preparing GSHHS")
    paths["gshhg"] = prepare_gshhg_root(
        Path(paths["gshhg"]) if paths.get("gshhg") else None,
        project_root / ".cache",
    )
    if paths["gshhg"] is None:
        raise FileNotFoundError(
            "GSHHS_h_L1.shp could not be prepared; execution stops before areas or densities are calculated."
        )
    if not bool(config["spatial"].get("clip_land_with_gshhg", True)):
        raise ValueError(
            "The GSHHS control is required and cannot be disabled in a complete cartographic run."
        )
    LOGGER.info("  [3.1] Reading MITECO cells near the records")
    grid, grid_inventory = load_grids(
        grid_root,
        params.grid_km,
        params.region,
        candidate_points,
        target_crs=int(config["spatial"]["target_crs"]),
        bbox_buffer_factor=float(
            config["spatial"].get("grid_bbox_buffer_factor", 1.25)
        ),
    )
    LOGGER.info("  [3.1] Candidate MITECO cells loaded: %d", len(grid))
    LOGGER.info("  [3.3] Actual marine area and persistent cache")
    grid, marine_area_qa = prepare_marine_grid_areas(
        grid,
        Path(paths["gshhg"]),
        cache_dir=project_root / ".cache",
        resolution_km=params.grid_km,
        progress_callback=lambda message: LOGGER.info("  [3.3] %s", message),
        marine_regions=regions,
    )
    LOGGER.info(
        "  [3.3] Completed: cache=%s; reused=%d; calculated=%d",
        marine_area_qa.get("marine_area_cache_status", "unknown"),
        marine_area_qa.get("marine_area_cache_cells_reused", 0),
        marine_area_qa.get("marine_area_cache_cells_computed", 0),
    )
    LOGGER.info("MITECO cells loaded around the records: %d", len(grid))
    tolerance = (
        params.grid_km
        * 1000
        * float(config["spatial"].get("nearest_tolerance_factor", 1.0))
    )
    LOGGER.info("[Preparation · 4/8] Assigning records to marine cells")
    assigned_all, unassigned, assignment_qa = assign_points_to_grid(
        candidate_points, grid, tolerance
    )
    # For records without a direct subdivision, the canonical 10-km reference
    # fixes regional membership before the analytical cell is considered.
    # Regional membership therefore does not change between 1/5/10 km.
    reference_region_mask = assigned_all.get(
        "region_scope_method", pd.Series("", index=assigned_all.index)
    ).astype("string").str.startswith("reference_grid_10km")
    if reference_region_mask.any():
        assigned_all.loc[reference_region_mask, "Region_slug"] = assigned_all.loc[
            reference_region_mask, "Region_slug_scope"
        ]
        assigned_all.loc[reference_region_mask, "Region_MITECO"] = assigned_all.loc[
            reference_region_mask, "Region_MITECO_scope"
        ]
        assigned_all.loc[reference_region_mask, "region_assignment_method"] = (
            "reference_grid_10km"
        )
    unresolved_region_mask = assigned_all.get(
        "region_scope_method", pd.Series("", index=assigned_all.index)
    ).astype("string").eq("unresolved")
    if unresolved_region_mask.any():
        assigned_all.loc[unresolved_region_mask, ["Region_slug", "Region_MITECO"]] = pd.NA
        assigned_all.loc[unresolved_region_mask, "region_assignment_method"] = "unresolved"
    assignment_qa["points_region_direct"] = int(
        assigned_all["region_assignment_method"].astype("string").eq("direct_point_intersection").sum()
    )
    assignment_qa["points_region_reference_10km"] = int(reference_region_mask.sum())
    assignment_qa["points_region_unresolved"] = int(unresolved_region_mask.sum())
    LOGGER.info(
        "Cells without positive marine surface excluded from assignment: %d; nearest-cell assignments: %d; points without a valid marine cell: %d",
        assignment_qa.get("grid_cells_excluded_no_marine_surface", 0),
        assignment_qa.get("points_nearest", 0),
        assignment_qa.get("points_unassigned", 0),
    )
    LOGGER.info(
        "MITECO fallback for GSHHS false zeros: %d cells available; %d observations retained in their original MITECO cell.",
        marine_area_qa.get("cells_using_miteco_demarcation_fallback", 0),
        assignment_qa.get("points_direct_miteco_fallback", 0),
    )
    assigned_area = pd.to_numeric(assigned_all["Area_mar_km2"], errors="coerce")
    invalid_assigned_area = assigned_area.isna() | assigned_area.le(0)
    if invalid_assigned_area.any():
        affected = (
            assigned_all.loc[invalid_assigned_area, "grid_id"]
            .dropna()
            .astype(str)
            .unique()
        )
        preview = ", ".join(affected[:10])
        raise ValueError(
            "Observations were assigned to cells without a validated positive marine surface. "
            f"Affected cells: {preview}. Execution stops to prevent incorrect densities."
        )
    assignment_audit, assignment_audit_summary, assignment_issue_cells, assignment_land = build_assignment_spatial_audit(
        candidate_points, grid, assigned_all, tolerance, Path(paths["gshhg"])
    )
    _csv2(
        assignment_audit,
        directories["07_debug"] / "spatial_assignment_audit_nearest_and_unassigned.csv",
    )
    _csv2(
        assignment_audit_summary,
        directories["07_debug"] / "spatial_assignment_audit_summary.csv",
    )
    qc_map_path = write_assignment_qc_map(
        directories["07_debug"] / "Spatial_Assignment_QC_Map.html",
        candidate_points,
        assigned_all,
        assignment_audit,
        assignment_issue_cells,
        assignment_land,
        title="Hispa-Syng · Spatial assignment quality control",
    )
    LOGGER.info(
        "Spatial assignment audit created: %d nearest assignments and %d unassigned points; QC map: %s",
        assignment_qa.get("points_nearest", 0),
        assignment_qa.get("points_unassigned", 0),
        qc_map_path,
    )
    outside_grid = unassigned.copy()
    outside_grid["grid_assignment_status"] = "Outside official marine grid"
    _csv2(
        _plain_table(outside_grid), directories["07_debug"] / "points_outside_grid.csv"
    )
    region_control = region_assignment_control(assigned_all)
    _csv2(
        region_control,
        directories["07_debug"] / "region_assignment_quality_control.csv",
    )
    if assignment_qa["points_region_unresolved"]:
        raise ValueError(
            "Some grid-assigned observations still have no official MITECO region; see region_assignment_quality_control.csv."
        )
    # Map 1 keeps every observation in the canonical regional scope, even
    # when it cannot be safely assigned to a cell at the selected analytical
    # resolution.
    map1_points = candidate_points.copy()
    map1_points["Region_slug_direct"] = map1_points["Region_slug"]
    map1_points["Region_MITECO_direct"] = map1_points["Region_MITECO"]
    map1_reference_mask = map1_points["region_scope_method"].astype("string").str.startswith(
        "reference_grid_10km"
    )
    map1_points.loc[map1_reference_mask, "Region_slug"] = map1_points.loc[
        map1_reference_mask, "Region_slug_scope"
    ]
    map1_points.loc[map1_reference_mask, "Region_MITECO"] = map1_points.loc[
        map1_reference_mask, "Region_MITECO_scope"
    ]
    map1_points["region_assignment_method"] = np.where(
        map1_reference_mask, "reference_grid_10km", "direct_point_intersection"
    )
    assignment_method_by_obs = (
        assigned_all.drop_duplicates("obs_id").set_index("obs_id")["assignment_method"]
        if not assigned_all.empty
        else pd.Series(dtype="object")
    )
    map1_points["grid_assignment_status"] = (
        map1_points["obs_id"].map(assignment_method_by_obs).fillna("unassigned")
    )
    map1_points = gpd.GeoDataFrame(
        add_species_authorities(map1_points), geometry="geometry", crs=map1_points.crs
    )
    map1_master = _plain_table(map1_points)

    assigned = filter_region(assigned_all, params.region)
    filter_counts["rows_after_region"] = int(len(assigned))
    event_summary = sampling_event_summary(assigned)
    filter_counts["sampling_events_after_region"] = int(event_summary["n_sampling_events"])
    _csv2(
        pd.DataFrame([event_summary]),
        directories["07_debug"] / "observation_event_proxy_summary.csv",
    )
    LOGGER.info(
        "Observation-event proxy: %d events for %d records (definition: date + normalized observer + EPSG:3035 position at ~1 m).",
        event_summary["n_sampling_events"],
        event_summary["n_records"],
    )
    _csv2(
        _plain_table(assigned), directories["04_tablas"] / "spatial_base" / "assigned_observations.csv"
    )
    LOGGER.info("Assigned observations: %d of %d", len(assigned), len(candidate_points))
    if assigned.empty:
        raise ValueError("No observation could be assigned to the MITECO grids.")

    points = gpd.GeoDataFrame(
        add_species_authorities(assigned), geometry="geometry", crs=assigned.crs
    )
    LOGGER.info(
        "Records in canonical regional scope: %d; assigned to cells for spatial analyses: %d; without a valid marine cell: %d",
        len(candidate_points), len(points), max(0, len(candidate_points) - len(points)),
    )

    master = _plain_table(points)
    _csv2(master, directories["04_tablas"] / "spatial_base" / "Filtered_Master_Database.csv")
    boundaries = boundaries_for_map(
        regions,
        params.region,
        float(config["maps"].get("simplify_boundaries_m", 100)),
    )
    logo_uri = logo_data_uri(Path(paths["logo"]) if paths.get("logo") else None)
    html_context = common_context(params, logo_uri)
    maps_only = bool(config.get("execution", {}).get("maps_only", False))
    download_targets = (
        {
            "map1": {
                "word": "../Web_Publication/downloads/Map1_Complete_Information.docx",
                "excel": "../Web_Publication/downloads/Map1_Complete_Information.xlsx",
                "data": "../Web_Publication/downloads/Map1_Complete_Information_Data_Package.zip",
            },
            "map2": {
                "word": "../Web_Publication/downloads/Map2_Complete_Information.docx",
                "excel": "../Web_Publication/downloads/Map2_Complete_Information.xlsx",
                "data": "../Web_Publication/downloads/Map2_Complete_Information_Data_Package.zip",
            },
            "map3": {
                "word": "../Web_Publication/downloads/Map3_Complete_Information.docx",
                "excel": "../Web_Publication/downloads/Map3_Complete_Information.xlsx",
                "data": "../Web_Publication/downloads/Map3_Complete_Information_Data_Package.zip",
            },
            "priority": {
                "word": "../../Web_Publication/downloads/Hispa_Syng_Priority_Areas_Report.docx",
                "excel": "../../Web_Publication/downloads/Priority_Conservation_Areas_Complete_Information.xlsx",
                "data": "../../Web_Publication/downloads/Priority_Conservation_Areas_Complete_Information_Data_Package.zip",
            },
        }
        if not maps_only
        else {}
    )
    html_context["map_downloads"] = download_targets
    LOGGER.info("[Preparation · 5/8] Cartographic context and observation map")
    cartographic_context = load_map_context(
        Path(paths["gshhg"]) if paths.get("gshhg") else None,
        points,
        float(config["maps"].get("simplify_coast_m", 200)),
    )
    LOGGER.info(
        "External coastal context: %s (custom land/coastline is not embedded in HTML).",
        cartographic_context.qa.get("status", "unknown"),
    )
    # Standalone maps accept these arguments as part of the public execution interface, but the
    # institutional HTML deliberately does not publish custom MITECO boundary
    # or land/coastline geometries.
    boundaries_for_html = {}
    coastline_for_html = {}

    map1_obs, map1_species, map1_colors = build_map1_observations(map1_master)
    html_context.update(
        n_records=int(len(map1_master)),
        n_species=int(len(map1_species)),
        species_list=map1_species,
        included_species=list(params.species_raw),
    )
    html_context["language_switch"] = _build_language_switch(run_root, params)
    LOGGER.info(
        "Map 1 will retain %d valid observations; %d are assigned to cells for spatial analyses.",
        len(map1_master), len(assigned),
    )
    map1_name = f"Map1_Observations_{params.grid_km}km_{params.year_tag}_{params.region}.html"
    map1_path = render_map1(
        directories["03_mapas"] / map1_name,
        map1_obs,
        map1_species,
        map1_colors,
        boundaries_for_html,
        coastline_for_html,
        html_context,
        params.open_browser,
        downloads=download_targets.get("map1"),
    )
    LOGGER.info("Map 1 created: %s", map1_path)

    LOGGER.info("[Preparation · 6/8] Metrics and densities from actual marine area")
    occupied, cell_metrics, species_metrics, sex_metrics, metric_qa = calculate_metrics(
        assigned, grid, params.grid_km
    )
    _csv2(cell_metrics, directories["04_tablas"] / "spatial_base" / "cell_metrics.csv")
    _csv2(species_metrics, directories["04_tablas"] / "spatial_base" / "cell_species_metrics.csv")
    _csv2(sex_metrics, directories["04_tablas"] / "spatial_base" / "cell_species_sex_metrics.csv")
    _csv2(
        cell_metrics[["grid_id", "n_obs_cell", "dist_mean", "Q_total", "calidad"]],
        directories["07_debug"] / "cell_quality_index.csv",
    )

    visual, land_qa = clip_occupied_cells_with_land(
        occupied,
        Path(paths["gshhg"]) if paths.get("gshhg") else None,
        bool(config["spatial"].get("clip_land_with_gshhg", True)),
        marine_regions=regions,
    )
    if visual.empty:
        raise ValueError("The display grid is empty after clipping with GSHHG.")
    visual["marine_geometry_method"] = str(land_qa.get("method", "unknown"))
    visual["marine_geometry_status"] = str(land_qa.get("status", "unknown"))
    visual["Area_geometria_marina_km2"] = visual.geometry.area / 1_000_000
    density_area = pd.to_numeric(visual["Area_mar_km2"], errors="coerce")
    geometry_area = pd.to_numeric(
        visual["Area_geometria_marina_km2"], errors="coerce"
    )
    area_source = visual.get("Area_mar_source", pd.Series("", index=visual.index)).astype("string")
    gshhs_mask = area_source.eq("gshhs_clipped_geometry")
    fallback_mask = area_source.eq("miteco_demarcation_fallback_geometry")
    area_matches = np.isclose(
        density_area.to_numpy(dtype=float),
        geometry_area.to_numpy(dtype=float),
        rtol=1e-10,
        atol=1e-9,
        equal_nan=False,
    )
    supported_area_source = gshhs_mask | fallback_mask
    valid_display_geometry = pd.Series(area_matches, index=visual.index) & supported_area_source
    if not bool(valid_display_geometry.all()):
        affected = visual.loc[~valid_display_geometry, "grid_id"].astype(str).tolist()
        raise AssertionError(
            "The density denominator is not backed by a valid marine display geometry. Affected cells: "
            + ", ".join(affected[:10])
        )
    land_qa["density_denominator_matches_displayed_marine_geometry"] = bool(
        pd.Series(area_matches, index=visual.index).loc[supported_area_source].all()
    )
    land_qa["miteco_fallback_display_geometry_valid"] = bool(
        pd.Series(area_matches, index=visual.index).loc[fallback_mask].all()
        if fallback_mask.any() else True
    )
    land_qa["maximum_density_area_difference_km2"] = float(
        (density_area - geometry_area).abs().max()
    )
    LOGGER.info(
        "Marine surface validated: %d cells; the density denominator matches the marine geometry used (GSHHS or MITECO fallback).",
        len(visual),
    )
    translate_geodataframe(visual).to_file(
        directories["02_intermedios"] / "occupied_cells.gpkg",
        layer="occupied_cells",
        driver="GPKG",
        engine="pyogrio",
    )

    LOGGER.info("[Preparation · 7/8] Density and variable maps")
    cells, all_species, dominant_colors, sex_species = cells_feature_collection(
        visual,
        species_metrics,
        sex_metrics,
        float(config["maps"].get("simplify_cells_m", 0)),
    )
    map2_name = f"Map2_Density_{params.grid_km}km_{params.year_tag}_{params.region}.html"
    map2_path = render_map2(
        directories["03_mapas"] / map2_name,
        cells,
        all_species,
        boundaries_for_html,
        coastline_for_html,
        html_context,
        params.open_browser,
        downloads=download_targets.get("map2"),
    )
    map3_name = (
        f"Map3_Variables_{params.grid_km}km_{params.year_tag}_{params.region}.html"
    )
    map3_path = render_map3(
        directories["03_mapas"] / map3_name,
        cells,
        dominant_colors,
        sex_species,
        boundaries_for_html,
        coastline_for_html,
        html_context,
        params.open_browser,
        downloads=download_targets.get("map3"),
    )
    LOGGER.info("Maps 2 and 3 created.")

    # The standalone map files in 03_maps are canonical.  The integrated
    # viewer references them from 08_viewers instead of materialising three
    # byte-identical copies there.
    viewer_map1_ref = f"../03_maps/{map1_path.name}"
    viewer_map2_ref = f"../03_maps/{map2_path.name}"
    viewer_map3_ref = f"../03_maps/{map3_path.name}"
    viewer_name = (
        f"Hippo_DEC_Viewer_{params.grid_km}km_{params.year_tag}_{params.region}.html"
    )
    analysis_outputs: dict[str, Any] | None = None
    publication_outputs: dict[str, Path] | None = None
    LOGGER.info("[Preparation · 8/8] Analysis, quality controls, and reports")
    if maps_only:
        LOGGER.info("Maps-only mode: analytical blocks 8–21 are skipped.")
        viewer_path = render_viewer(
            directories["08_visores"] / viewer_name,
            viewer_map1_ref,
            viewer_map2_ref,
            viewer_map3_ref,
            None,
            None,
            html_context,
            params.open_browser,
        )
    else:
        # Deferred imports preserve the lightweight maps-only startup path.
        from .analysis_pipeline import run_full_analysis
        from .web_publication import build_web_publication

        official_multiscale_grids, multiscale_grid_preparation_qa = _prepare_official_multiscale_grids(
            grid_root=grid_root,
            selected_grid=grid,
            selected_grid_km=params.grid_km,
            selected_region=params.region,
            points=assigned,
            config=config,
            gshhg_path=Path(paths["gshhg"]),
            cache_dir=project_root / ".cache",
            marine_regions=regions,
        )
        _csv2(
            multiscale_grid_preparation_qa,
            directories["07_debug"] / "official_multiscale_grid_preparation.csv",
        )
        analysis_outputs = run_full_analysis(
            run_root=run_root,
            directories=directories,
            config=config,
            paths=paths,
            assigned=assigned,
            occupied_cells=occupied,
            cell_metrics=cell_metrics,
            cartographic_context=cartographic_context,
            html_context=html_context,
            selected_grid_km=params.grid_km,
            official_marine_cells=visual,
            official_multiscale_grids=official_multiscale_grids,
            marine_mask=grid,
        )
        priority_viewer_copy = Path(shutil.copy2(
            analysis_outputs["priority_map"],
            directories["08_visores"] / analysis_outputs["priority_map"].name,
        ))
        # The priority map is rendered under 09_priority_conservation_areas,
        # where ../../Web_Publication/downloads is correct.  Its standalone
        # copy lives in 08_viewers, so adjust only that copy's links before it
        # is exposed as an independent institutional-viewer entry point.
        priority_text = priority_viewer_copy.read_text(encoding="utf-8")
        priority_text = priority_text.replace(
            "../../Web_Publication/downloads/",
            "../Web_Publication/downloads/",
        )
        priority_viewer_copy.write_text(priority_text, encoding="utf-8")
        rewrite_language_switch(
            priority_viewer_copy,
            html_context.get("language_switch"),
            priority_viewer_copy,
            "priority",
        )
        copy_public_registration(analysis_outputs["priority_map"], priority_viewer_copy)
        manual_candidates = [
            project_root / "Manual_Hispa_Syng_v1_0_EN.docx",
            project_root / "Manual_Hispa_Syng_v1_0_EN.pdf",
        ]
        publication_outputs = build_web_publication(
            run_root=run_root,
            context=html_context,
            map_paths={
                "map1": map1_path,
                "map2": map2_path,
                "map3": map3_path,
                "priority": analysis_outputs["priority_map"],
            },
            master=map1_master,
            assigned=assigned,
            outside_grid=outside_grid,
            occupied=occupied,
            species_metrics=species_metrics,
            sex_metrics=sex_metrics,
            conservation=analysis_outputs["conservation"],
            logo=Path(paths["logo"]) if paths.get("logo") else None,
            manual_paths=manual_candidates,
            open_browser=params.open_browser,
        )
        download_links = {
            key: {
                "word": f"../Web_Publication/downloads/{publication_outputs[f'{key}_word'].name}",
                "excel": f"../Web_Publication/downloads/{publication_outputs[f'{key}_excel'].name}",
                "data": f"../Web_Publication/downloads/{publication_outputs[f'{key}_data'].name}",
            }
            for key in ("map1", "map2", "map3", "priority")
        }
        viewer_path = render_viewer(
            directories["08_visores"] / viewer_name,
            viewer_map1_ref,
            viewer_map2_ref,
            viewer_map3_ref,
            Path(priority_viewer_copy).name,
            download_links,
            html_context,
            False,
        )

    habitat_untranslated = [
        "Arena",
        "Pradera marina",
        "Rocas",
        "No determinado",
        "Antrópico",
        "Pelágico",
        "Sin región",
    ]
    # Leaflet is distributed locally. The Satellite (Esri World Imagery),
    # Physical (OpenTopoMap), and Marine bathymetry (EMODnet Bathymetry) basemaps
    # are requested online when the HTML opens; they do not participate in calculations.
    offline_map_forbidden = [
        "https://unpkg.com/leaflet",
        "url(images/",
    ]
    html_qa = [
        _validate_html(
            map1_path,
            ["Map 1", "observations", "leaflet"],
            offline_map_forbidden,
            scoped_fields=("habitat",),
            scoped_forbidden=habitat_untranslated,
        ),
        _validate_html(
            map2_path,
            ["Map 2", "cells", "Density"],
            offline_map_forbidden,
        ),
        _validate_html(
            map3_path,
            ["Map 3", "dominantColors", "Sex composition"],
            offline_map_forbidden,
        ),
        _validate_html(
            viewer_path,
            [viewer_map1_ref, viewer_map2_ref, viewer_map3_ref]
            + ([analysis_outputs["priority_map"].name, "Download Word", "Download Excel", "Download Data ZIP"] if analysis_outputs else []),
        ),
    ]
    if analysis_outputs:
        html_qa.append(
            _validate_html(
                analysis_outputs["priority_map"],
                [
                    "const cells=",
                    "Leaflet 1.9.4",
                    "overviewLayer",
                    "Overview symbols",
                    "tile.opentopomap.org",
                    "tiles.emodnet-bathymetry.eu",
                    "World_Imagery",
                ],
                offline_map_forbidden + [
                    "const land=",
                    "Tierra GSHHG",
                    "folium",
                    "jquery",
                    "bootstrap",
                ],
                scoped_fields=("habitat_dominante_grid", "habitat_dominant_zone"),
                scoped_forbidden=habitat_untranslated,
            )
        )
    qa = {
        "status": "passed",
        "input": input_summary,
        "filters": filter_counts,
        "assignment": assignment_qa,
        "region_assignment_quality_control": str(
            directories["07_debug"] / "region_assignment_quality_control.csv"
        ),
        "metrics": metric_qa,
        "marine_area": marine_area_qa,
        "land_clip": land_qa,
        "map_context": cartographic_context.qa,
        "grid_inventory": grid_inventory,
        "html": html_qa,
        "analysis": {
            "mode": "maps_only" if maps_only else "complete",
            "status": "skipped" if maps_only else "passed",
            "qa": str(analysis_outputs["qa"]) if analysis_outputs else None,
            "manifest": str(analysis_outputs["manifest"]) if analysis_outputs else None,
            "regional_data_quality_control": str(analysis_outputs["regional_data_quality_control"])
            if analysis_outputs
            else None,
            "runtime_warning_control": str(analysis_outputs["runtime_warning_control"])
            if analysis_outputs
            else None,
            "duplicate_output_control": str(analysis_outputs["duplicate_output_control"])
            if analysis_outputs
            else None,
            "duplicates_removed": len(analysis_outputs["duplicates_removed"])
            if analysis_outputs
            else 0,
        },
        "versions": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "geopandas": gpd.__version__,
        },
    }
    (directories["07_debug"] / "qa_summary.json").write_text(
        json.dumps(_presentation_json(qa), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    snapshot = {
        "run_parameters": asdict(params),
        "resolved_paths": {
            key: str(value) if value is not None else None
            for key, value in paths.items()
        },
        "configuration": config,
    }
    (directories["01_parametros"] / "run_info.yaml").write_text(
        yaml.safe_dump(snapshot, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    LOGGER.info("Quality control completed: PASS")
    LOGGER.info("Integrated viewer: %s", viewer_path)
    outputs = {
        "run_root": run_root,
        "map1": map1_path,
        "map2": map2_path,
        "map3": map3_path,
        "viewer": publication_outputs["index"] if publication_outputs else viewer_path,
        "qa": directories["07_debug"] / "qa_summary.json",
    }
    if analysis_outputs:
        outputs.update(
            {
                "analysis_qa": analysis_outputs["qa"],
                "analysis_manifest": analysis_outputs["manifest"],
                "priority_map": analysis_outputs["priority_map"],
                "priority_report": analysis_outputs["priority_report"],
                "web_publication": publication_outputs["root"],
                "web_index": publication_outputs["index"],
                "viewer_copy": viewer_path,
            }
        )
        from .analysis_io import cleanup_figure_temporaries

        cleanup_figure_temporaries(run_root)
    return outputs
