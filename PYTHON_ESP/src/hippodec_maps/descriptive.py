"""Bloques 8 y 9: descripción, hábitat, profundidad y figuras de referencia."""

from __future__ import annotations

import math
import logging
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import shapely
from scipy import stats
from statsmodels.stats.multitest import multipletests

from .analysis_io import OutputRegistry, csv2, excel_book, save_figure, table_pair, text_file
from .analysis_utils import AnalysisSettings, bootstrap_median_ci, numeric, shannon, simpson
from .localization import translate_habitat_value

LOGGER = logging.getLogger("hippodec_maps")


DEPTH_BINS = [-np.inf, 1, 5, 10, 20, 50, np.inf]
DEPTH_LABELS = ["0–1 m", "1–5 m", "5–10 m", "10–20 m", "20–50 m", ">50 m"]


def _abundance(table: pd.DataFrame) -> pd.Series:
    return numeric(table["N_total"], fill=0).clip(lower=0)


def _group_summary(table: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    working = table.copy()
    working["abundance_aux"] = _abundance(working)
    return (
        working.groupby(columns, dropna=False, observed=True)
        .agg(
            n_records=("grid_id", "size"),
            abundance=("abundance_aux", "sum"),
            richness=("Species", "nunique"),
            occupied_cells=("grid_id", "nunique"),
        )
        .reset_index()
    )


def _depth_summary(
    table: pd.DataFrame,
    group_columns: list[str],
    settings: AnalysisSettings,
    seed_offset: int = 0,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    grouped = table.groupby(group_columns, dropna=False, observed=True) if group_columns else [((), table)]
    for index, (key, group) in enumerate(grouped):
        values = numeric(group["Depth"]).to_numpy(dtype=float)
        values = values[np.isfinite(values) & (values >= 0)]
        if not isinstance(key, tuple):
            key = (key,)
        row = {name: value for name, value in zip(group_columns, key)}
        low, high = bootstrap_median_ci(
            values, settings.bootstrap_iterations, settings.random_seed + seed_offset + index
        )
        row.update(
            {
                "n_depth_valid": int(values.size),
                "calculation_status": "calculable" if values.size else "not_calculable",
                "calculation_note": (
                    "Hay al menos un valor numérico de profundidad no negativo disponible."
                    if values.size
                    else "No existe un valor numérico de profundidad no negativo para este grupo; las estadísticas de profundidad y los intervalos de confianza no son calculables."
                ),
                "depth_mean": float(np.mean(values)) if values.size else np.nan,
                "depth_sd": float(np.std(values, ddof=1)) if values.size > 1 else np.nan,
                "depth_median": float(np.median(values)) if values.size else np.nan,
                "depth_q25": float(np.quantile(values, 0.25)) if values.size else np.nan,
                "depth_q75": float(np.quantile(values, 0.75)) if values.size else np.nan,
                "depth_min": float(np.min(values)) if values.size else np.nan,
                "depth_max": float(np.max(values)) if values.size else np.nan,
                "median_ci_low": low,
                "median_ci_high": high,
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def _safe_kruskal(table: pd.DataFrame, value: str, group: str) -> dict[str, Any]:
    pieces = [
        numeric(frame[value]).dropna().to_numpy(dtype=float)
        for _, frame in table.groupby(group, observed=True)
    ]
    pieces = [piece for piece in pieces if len(piece) >= 2]
    if len(pieces) < 2:
        return {"test": "Kruskal-Wallis", "variable": value, "group": group, "statistic": np.nan, "p_value": np.nan, "n_groups": len(pieces)}
    result = stats.kruskal(*pieces)
    return {"test": "Kruskal-Wallis", "variable": value, "group": group, "statistic": float(result.statistic), "p_value": float(result.pvalue), "n_groups": len(pieces)}


def _spearman(table: pd.DataFrame, first: str, second: str) -> dict[str, Any]:
    valid = table[[first, second]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(valid) < 3 or valid[first].nunique() < 2 or valid[second].nunique() < 2:
        return {"variable_1": first, "variable_2": second, "rho": np.nan, "p_value": np.nan, "n": len(valid)}
    result = stats.spearmanr(valid[first], valid[second])
    return {"variable_1": first, "variable_2": second, "rho": float(result.statistic), "p_value": float(result.pvalue), "n": len(valid)}


def _linear_trend(table: pd.DataFrame, response: str, predictor: str) -> dict[str, Any]:
    valid = table[[response, predictor]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(valid) < 3 or valid[predictor].nunique() < 2:
        return {"response": response, "predictor": predictor, "slope": np.nan, "intercept": np.nan, "R2": np.nan, "p_value": np.nan, "n": len(valid)}
    result = stats.linregress(valid[predictor], valid[response])
    return {"response": response, "predictor": predictor, "slope": float(result.slope), "intercept": float(result.intercept), "R2": float(result.rvalue**2), "p_value": float(result.pvalue), "n": len(valid)}


def _pairwise_mannwhitney(table: pd.DataFrame, value: str, group: str) -> pd.DataFrame:
    groups = [(str(name), pd.to_numeric(frame[value], errors="coerce").dropna().to_numpy()) for name, frame in table.groupby(group, observed=True)]
    groups = [(name, values) for name, values in groups if len(values) >= 2]
    rows: list[dict[str, Any]] = []
    for index, (first_name, first) in enumerate(groups):
        for second_name, second in groups[index + 1 :]:
            result = stats.mannwhitneyu(first, second, alternative="two-sided")
            rows.append({"group_1": first_name, "group_2": second_name, "W": float(result.statistic), "p_value": float(result.pvalue), "n_1": len(first), "n_2": len(second)})
    output = pd.DataFrame(rows)
    if not output.empty:
        output["p_adjust_BH"] = multipletests(output["p_value"], method="fdr_bh")[1]
    return output


def _chi_square(table: pd.DataFrame, row: str, column: str) -> pd.DataFrame:
    contingency = pd.crosstab(table[row], table[column])
    if contingency.shape[0] < 2 or contingency.shape[1] < 2:
        return pd.DataFrame([{"row": row, "column": column, "chi2": np.nan, "df": np.nan, "p_value": np.nan, "n": int(contingency.to_numpy().sum())}])
    chi2, p_value, dof, _ = stats.chi2_contingency(contingency)
    return pd.DataFrame([{"row": row, "column": column, "chi2": float(chi2), "df": int(dof), "p_value": float(p_value), "n": int(contingency.to_numpy().sum())}])


def _coast_distance(
    cell_geometry: gpd.GeoDataFrame,
    gshhg_path: Path | None,
) -> pd.DataFrame:
    cells = cell_geometry[["grid_id", "geometry"]].drop_duplicates("grid_id").copy()
    if gshhg_path is None:
        return pd.DataFrame(
            {
                "grid_id": cells["grid_id"].astype(str),
                "distance_to_coast_m": np.nan,
                "calculation_status": "not_calculable",
                "method": "No se ha suministrado litoral externo; se conservan las celdas marinas oficiales MITECO.",
            }
        )
    geographic_bbox = tuple(cells.to_crs(4326).total_bounds)
    coast = gpd.read_file(gshhg_path, bbox=geographic_bbox, engine="pyogrio")
    if coast.empty:
        return pd.DataFrame(
            {
                "grid_id": cells["grid_id"].astype(str),
                "distance_to_coast_m": np.nan,
                "calculation_status": "not_calculable",
                "method": "GSHHG no devolvió geometría de litoral para la extensión del estudio.",
            }
        )
    coast = coast.to_crs(cells.crs)
    boundary = coast.geometry.boundary.union_all()
    centroids = cells.geometry.centroid.array
    distances = shapely.distance(centroids, boundary)
    return pd.DataFrame(
        {
            "grid_id": cells["grid_id"].astype(str),
            "distance_to_coast_m": distances,
            "calculation_status": "calculable",
                "method": "Distancia desde el centroide de la celda al límite de litoral GSHHG.",
        }
    )


def _community_by_region(assigned: pd.DataFrame) -> pd.DataFrame:
    matrix = assigned.assign(abundance_aux=_abundance(assigned)).pivot_table(
        index="Region_MITECO", columns="Species", values="abundance_aux", aggfunc="sum", fill_value=0
    )
    rows: list[dict[str, Any]] = []
    for region, values in matrix.iterrows():
        x = values.to_numpy(dtype=float)
        richness = int(np.count_nonzero(x > 0))
        h = shannon(x)
        rows.append(
            {
                "Region_MITECO": region,
                "richness": richness,
                "abundance": float(x.sum()),
                "shannon": h,
                "simpson": simpson(x),
                "pielou": h / math.log(richness) if richness > 1 else 0.0,
            }
        )
    return pd.DataFrame(rows)


def run_descriptive_analysis(
    assigned: gpd.GeoDataFrame,
    occupied_cells: gpd.GeoDataFrame,
    directories: dict[str, Path],
    gshhg_path: Path | None,
    settings: AnalysisSettings,
    registry: OutputRegistry,
) -> dict[str, Any]:
    LOGGER.info("    [1/8 · 1/4] Preparación de variables descriptivas")
    table = pd.DataFrame(assigned.drop(columns="geometry")).copy()
    table["grid_id"] = table["grid_id"].astype(str)
    table["year"] = pd.to_datetime(table["Fecha_aux"], errors="coerce").dt.year.astype("Int64")
    table["abundance_aux"] = _abundance(table)
    table["Habitat_clean"] = table.get("Habitat", pd.Series(pd.NA, index=table.index)).astype("string").str.strip()
    table["Habitat_clean"] = table["Habitat_clean"].mask(table["Habitat_clean"].isin(["", "NA", "<NA>"]))
    table["Depth"] = numeric(table["Depth"])
    table.loc[table["Depth"] < 0, "Depth"] = np.nan

    table_dir = directories["04_tablas"] / "descriptivo_habitat_profundidad"
    figure_dir = directories["05_figuras"] / "descriptivo_habitat_profundidad"
    model_dir = directories["06_modelos"] / "descriptivo_habitat_profundidad"

    LOGGER.info("    [1/8 · 2/4] Resúmenes de esfuerzo, especies, hábitat y costa")
    effort = (
        table.groupby("year", dropna=False)
        .agg(
            n_records=("grid_id", "size"),
            abundance=("abundance_aux", "sum"),
            richness=("Species", "nunique"),
            occupied_cells=("grid_id", "nunique"),
            observers=("Observer", "nunique"),
        )
        .reset_index()
        .sort_values("year")
    )
    region_summary = _group_summary(table, ["Region_MITECO"])
    species_global = _group_summary(table, ["Species"]).rename(columns={"n_records": "frequency_records"})
    species_global["occupancy_pct_sampled_cells"] = 100 * species_global["occupied_cells"] / max(table["grid_id"].nunique(), 1)
    species_distribution = (
        table.groupby("Species", observed=True)
        .agg(
            latitude_min=("Latitude", "min"), latitude_max=("Latitude", "max"),
            longitude_min=("Longitude", "min"), longitude_max=("Longitude", "max"),
            first_year=("year", "min"), last_year=("year", "max"),
            n_regions=("Region_MITECO", "nunique"),
        )
        .reset_index()
        .merge(species_global, on="Species", how="left")
    )
    dominance = _group_summary(table, ["Region_MITECO", "Species"])
    dominance["regional_abundance"] = dominance.groupby("Region_MITECO")["abundance"].transform("sum")
    dominance["relative_abundance_pct"] = 100 * dominance["abundance"] / dominance["regional_abundance"].replace(0, np.nan)
    dominance["rank_region"] = dominance.groupby("Region_MITECO")["abundance"].rank(method="dense", ascending=False).astype("Int64")
    habitat = _group_summary(table.dropna(subset=["Habitat_clean"]), ["Species", "Habitat_clean"])
    habitat["species_habitat_records"] = habitat.groupby("Species")["n_records"].transform("sum")
    habitat["relative_frequency_pct"] = 100 * habitat["n_records"] / habitat["species_habitat_records"].replace(0, np.nan)
    dominant_habitat = habitat.sort_values(["Species", "n_records", "Habitat_clean"], ascending=[True, False, True]).drop_duplicates("Species")

    coast_distance = _coast_distance(occupied_cells, gshhg_path)
    coastal_ids = set(coast_distance.loc[coast_distance["distance_to_coast_m"] <= settings.coastal_threshold_km * 1000, "grid_id"])
    coastal = table[table["grid_id"].isin(coastal_ids)].copy()
    coastal_denominator = (
        coastal[["Region_MITECO", "grid_id"]]
        .drop_duplicates()
        .groupby("Region_MITECO")
        .size()
        .rename("sampled_coastal_cells")
        .reset_index()
    )
    coastal_occupancy = _group_summary(coastal, ["Region_MITECO", "Species"]).merge(coastal_denominator, on="Region_MITECO", how="left")
    coastal_occupancy["coastal_occupancy_pct"] = 100 * coastal_occupancy["occupied_cells"] / coastal_occupancy["sampled_coastal_cells"].replace(0, np.nan)
    community_region = _community_by_region(table)

    depth_global = _depth_summary(table, [], settings)
    depth_species = _depth_summary(table, ["Species"], settings, 1000)
    depth_region = _depth_summary(table, ["Region_MITECO"], settings, 2000)
    depth_year = _depth_summary(table.dropna(subset=["year"]), ["year"], settings, 3000)
    depth_habitat = _depth_summary(table.dropna(subset=["Habitat_clean"]), ["Habitat_clean"], settings, 4000)
    depth_species_habitat = _depth_summary(table.dropna(subset=["Habitat_clean"]), ["Species", "Habitat_clean"], settings, 5000)
    table["depth_class"] = pd.cut(table["Depth"], bins=DEPTH_BINS, labels=DEPTH_LABELS, right=False)
    depth_classes = _group_summary(table.dropna(subset=["depth_class"]), ["Species", "depth_class"])

    LOGGER.info("    [1/8 · 3/4] Contrastes de profundidad y asociaciones")
    tests: list[dict[str, Any]] = [
        _safe_kruskal(table, "Depth", "Species"),
        _safe_kruskal(table, "Depth", "Region_MITECO"),
        _safe_kruskal(table.dropna(subset=["Habitat_clean"]), "Depth", "Habitat_clean"),
    ]
    valid_depth_abundance = table[["Depth", "abundance_aux"]].dropna()
    if len(valid_depth_abundance) >= 3 and valid_depth_abundance.nunique().min() > 1:
        correlation = stats.spearmanr(valid_depth_abundance["Depth"], valid_depth_abundance["abundance_aux"])
        tests.append({"test": "Spearman", "variable": "Depth", "group": "N_total", "statistic": float(correlation.statistic), "p_value": float(correlation.pvalue), "n_groups": len(valid_depth_abundance)})
    valid_year = table[["Depth", "year"]].dropna()
    if len(valid_year) >= 3 and valid_year["year"].nunique() > 1:
        trend = stats.linregress(valid_year["year"].astype(float), valid_year["Depth"])
        tests.append({"test": "Regresión lineal", "variable": "Depth", "group": "year", "statistic": float(trend.slope), "p_value": float(trend.pvalue), "n_groups": len(valid_year)})
    contingency = pd.crosstab(table["Species"], table["depth_class"])
    if contingency.shape[0] > 1 and contingency.shape[1] > 1:
        chi = stats.chi2_contingency(contingency)
        tests.append({"test": "Chi-cuadrado", "variable": "Species", "group": "depth_class", "statistic": float(chi.statistic), "p_value": float(chi.pvalue), "n_groups": int(contingency.size)})
    depth_tests = pd.DataFrame(tests)

    # Paridad detallada con los subapartados 8.14.10–8.14.14 del script R.
    depth_pairwise_species = _pairwise_mannwhitney(table, "Depth", "Species")
    depth_pairwise_region = _pairwise_mannwhitney(table, "Depth", "Region_MITECO")
    depth_chi_species = _chi_square(table.dropna(subset=["Species", "depth_class"]), "Species", "depth_class")
    depth_spearman_year = pd.DataFrame([_spearman(table, "Depth", "year")])
    depth_lm_year = pd.DataFrame([_linear_trend(table, "Depth", "year")])
    depth_spearman_abundance = pd.DataFrame([_spearman(table, "Depth", "abundance_aux")])

    species_test_rows: list[dict[str, Any]] = []
    species_region_tests: list[dict[str, Any]] = []
    species_year_tests: list[dict[str, Any]] = []
    species_abundance_tests: list[dict[str, Any]] = []
    for species, subset in table.groupby("Species", observed=True):
        region_test = _safe_kruskal(subset, "Depth", "Region_MITECO")
        region_test["Species"] = species
        species_region_tests.append(region_test)
        year_test = _spearman(subset, "Depth", "year")
        year_test["Species"] = species
        species_year_tests.append(year_test)
        abundance_test = _spearman(subset, "Depth", "abundance_aux")
        abundance_test["Species"] = species
        species_abundance_tests.append(abundance_test)
        species_test_rows.append(
            {
                "Species": species,
                "n_depth_valid": int(subset["Depth"].notna().sum()),
                "n_regions": int(subset.loc[subset["Depth"].notna(), "Region_MITECO"].nunique()),
                "n_years": int(subset.loc[subset["Depth"].notna(), "year"].nunique()),
                "region_test_available": pd.notna(region_test.get("p_value")),
                "year_test_available": pd.notna(year_test.get("p_value")),
                "abundance_test_available": pd.notna(abundance_test.get("p_value")),
            }
        )
    depth_region_by_species = pd.DataFrame(species_region_tests)
    depth_year_by_species = pd.DataFrame(species_year_tests)
    depth_abundance_by_species = pd.DataFrame(species_abundance_tests)
    depth_test_status = pd.DataFrame(species_test_rows)

    habitat_region = _group_summary(table.dropna(subset=["Habitat_clean"]), ["Region_MITECO", "Habitat_clean"])
    habitat_depth_class = _group_summary(table.dropna(subset=["Habitat_clean", "depth_class"]), ["Habitat_clean", "depth_class"])
    habitat_traceability = (
        table.assign(Habitat_original=table.get("Habitat", pd.Series(pd.NA, index=table.index)))
        .groupby(["Habitat_original", "Habitat_clean"], dropna=False, observed=True)
        .size().rename("n_records").reset_index()
    )
    habitat_specialization = (
        habitat.groupby("Species", observed=True)
        .agg(
            n_habitats=("Habitat_clean", "nunique"),
            dominant_habitat_pct=("relative_frequency_pct", "max"),
            habitat_shannon=("relative_frequency_pct", lambda values: shannon(np.asarray(values, dtype=float))),
        )
        .reset_index()
    )
    habitat_specialization["apparent_specialization"] = np.select(
        [habitat_specialization["dominant_habitat_pct"] >= 75, habitat_specialization["dominant_habitat_pct"] >= 50],
        ["Alta", "Moderada"],
        default="Baja",
    )
    habitat_species_test = _chi_square(table.dropna(subset=["Species", "Habitat_clean"]), "Species", "Habitat_clean")
    habitat_depth_test = pd.DataFrame([_safe_kruskal(table.dropna(subset=["Habitat_clean"]), "Depth", "Habitat_clean")])
    habitat_depth_species_tests: list[dict[str, Any]] = []
    for species, subset in table.dropna(subset=["Habitat_clean"]).groupby("Species", observed=True):
        result = _safe_kruskal(subset, "Depth", "Habitat_clean")
        result["Species"] = species
        habitat_depth_species_tests.append(result)
    habitat_depth_species_test = pd.DataFrame(habitat_depth_species_tests)

    completeness = pd.DataFrame(
        {
            "variable": ["Depth", "Habitat", "Temperatura_gC", "N_total", "sexo"],
            "n_valid": [
                int(table["Depth"].notna().sum()),
                int(table["Habitat_clean"].notna().sum()),
                int(numeric(table["Temperatura_gC"]).notna().sum()),
                int(numeric(table["N_total"]).notna().sum()),
                int((numeric(table["N hembra"], 0) + numeric(table["N macho"], 0) + numeric(table["N_indeterminado"], 0) > 0).sum()),
            ],
        }
    )
    completeness["n_total"] = len(table)
    completeness["completeness_pct"] = 100 * completeness["n_valid"] / max(len(table), 1)

    tables: dict[str, pd.DataFrame] = {
        "Esfuerzo_temporal": effort,
        "Resumen_regiones": region_summary,
        "Frecuencia_especies": species_global,
        "Distribucion_especies": species_distribution,
        "Dominancia_regional": dominance,
        "Habitat_especie": habitat,
        "Habitat_dominante": dominant_habitat,
        "Distancia_costa": coast_distance,
        "Denominador_costero": coastal_denominator,
        "Ocupacion_costera": coastal_occupancy,
        "Indices_comunidad_region": community_region,
        "Depth_global": depth_global,
        "Depth_especie": depth_species,
        "Depth_region": depth_region,
        "Depth_anio": depth_year,
        "Depth_habitat": depth_habitat,
        "Depth_especie_habitat": depth_species_habitat,
        "Classs_batimetricas": depth_classes,
        "Tests_depth_habitat": depth_tests,
        "Depth_pairwise_species": depth_pairwise_species,
        "Depth_pairwise_region": depth_pairwise_region,
        "Depth_chi_species_clase": depth_chi_species,
        "Depth_spearman_year": depth_spearman_year,
        "Depth_lm_year": depth_lm_year,
        "Depth_spearman_abundance": depth_spearman_abundance,
        "Depth_region_por_especie": depth_region_by_species,
        "Depth_year_por_especie": depth_year_by_species,
        "Depth_abundance_por_especie": depth_abundance_by_species,
        "Depth_estado_tests_especie": depth_test_status,
        "Habitat_region": habitat_region,
        "Habitat_depth_class": habitat_depth_class,
        "Habitat_trazabilidad": habitat_traceability,
        "Habitat_especializacion": habitat_specialization,
        "Test_species_habitat": habitat_species_test,
        "Test_habitat_depth": habitat_depth_test,
        "Test_species_habitat_depth": habitat_depth_species_test,
        "Completitud": completeness,
    }
    book_path = excel_book(tables, table_dir / "Tablas_08_Analisis_Descriptivo_Habitat_Profundidad.xlsx")
    registry.add(book_path, "8", "Libro completo del análisis descriptivo, de hábitat y de profundidad")
    for name, frame in tables.items():
        path = csv2(frame, table_dir / f"Table_08_{name}.csv")
        registry.add(path, "8", f"Tabla {name.replace('_', ' ')}")

    report = (
        "ANÁLISIS DESCRIPTIVO, DE HÁBITAT Y DE PROFUNDIDAD\n"
        f"Registros analizados: {len(table)}\n"
        f"Especies: {table['Species'].nunique()}\n"
        f"Celdas muestreadas: {table['grid_id'].nunique()}\n"
        f"Registros con profundidad válida: {table['Depth'].notna().sum()} ({100 * table['Depth'].notna().mean():.1f} %)\n"
        f"Registros con hábitat: {table['Habitat_clean'].notna().sum()} ({100 * table['Habitat_clean'].notna().mean():.1f} %)\n"
        f"Dominio costero: ≤{settings.coastal_threshold_km:g} km; denominador = celdas costeras muestreadas por región.\n"
        "Las pruebas son exploratorias y no corrigen el sesgo del esfuerzo de muestreo salvo cuando se indique expresamente.\n"
    )
    report_path = text_file(report, model_dir / "Informe_08_Analisis_Descriptivo_Habitat_Profundidad.txt")
    registry.add(report_path, "8", "Informe metodológico e interpretativo del bloque descriptivo")

    if not effort.empty:
        fig, ax1 = plt.subplots(figsize=(10, 5.5))
        sns.lineplot(data=effort, x="year", y="n_records", marker="o", ax=ax1, color="#2468a2", label="Registros")
        ax1.set(xlabel="Año", ylabel="Número de registros", title="Esfuerzo de observación temporal")
        for path in save_figure(fig, figure_dir / "Figure_09_01_Temporal_Effort"):
            registry.add(path, "9", "Figura de esfuerzo temporal")

    if not region_summary.empty:
        fig, ax = plt.subplots(figsize=(10, 5.5))
        ordered = region_summary.sort_values("richness", ascending=False)
        sns.barplot(data=ordered, x="richness", y="Region_MITECO", color="#2a9d8f", ax=ax)
        ax.set(xlabel="Riqueza observada", ylabel="Región", title="Riqueza específica por demarcación MITECO")
        for path in save_figure(fig, figure_dir / "Figure_09_02_Richness_by_Region"):
            registry.add(path, "9", "Figura de riqueza por región")

    if not species_global.empty:
        fig, ax = plt.subplots(figsize=(9, 6.5))
        ordered = species_global.sort_values("occupancy_pct_sampled_cells")
        sns.barplot(data=ordered, x="occupancy_pct_sampled_cells", y="Species", color="#e9c46a", ax=ax)
        ax.set(xlabel="Ocupación (% de celdas muestreadas)", ylabel="Especie", title="Ocupación espacial global")
        for path in save_figure(fig, figure_dir / "Figure_09_03_Overall_Species_Occupancy"):
            registry.add(path, "9", "Figura de ocupación global por especie")

    if not dominance.empty:
        heat = dominance.pivot(index="Species", columns="Region_MITECO", values="relative_abundance_pct").fillna(0).astype(float)
        fig, ax = plt.subplots(figsize=(max(9, 1.6 * heat.shape[1]), max(6, 0.45 * heat.shape[0])))
        sns.heatmap(heat, cmap="YlOrRd", annot=True, fmt=".1f", ax=ax, cbar_kws={"label": "% regional"})
        ax.set(title="Dominancia relativa por región", xlabel="Región MITECO", ylabel="Especie")
        for path in save_figure(fig, figure_dir / "Figure_09_04_Regional_Dominance"):
            registry.add(path, "9", "Mapa de calor de dominancia regional")

    depth_plot = table.dropna(subset=["Depth", "Species"])
    depth_species_order: list[str] = []
    if not depth_plot.empty:
        # Use one common bathymetric order across all depth-by-species figures.
        # Primary criterion: median depth (deepest to shallowest).
        # Ties: mean depth (deepest to shallowest), then scientific name.
        depth_order_stats = (
            depth_plot.groupby("Species", as_index=False)["Depth"]
            .agg(depth_median="median", depth_mean="mean")
            .sort_values(
                ["depth_median", "depth_mean", "Species"],
                ascending=[False, False, True],
                kind="mergesort",
            )
        )
        depth_species_order = depth_order_stats["Species"].astype(str).tolist()
        fig, ax = plt.subplots(figsize=(10, max(6, 0.45 * depth_plot["Species"].nunique())))
        sns.boxplot(
            data=depth_plot,
            x="Depth",
            y="Species",
            order=depth_species_order,
            showfliers=False,
            color="#8ecae6",
            ax=ax,
        )
        ax.set(xlabel="Profundidad observada (m)", ylabel="Especie", title="Distribución batimétrica por especie")
        for path in save_figure(fig, figure_dir / "Figure_09_05_Depth_by_Species"):
            registry.add(path, "9", "Diagrama de caja de profundidad por especie")

    if not habitat.empty:
        plot_habitat = habitat.copy()
        plot_habitat["Habitat_clean"] = plot_habitat["Habitat_clean"].map(translate_habitat_value)
        heat = plot_habitat.pivot(index="Species", columns="Habitat_clean", values="relative_frequency_pct").fillna(0).astype(float)
        fig, ax = plt.subplots(figsize=(max(10, 1.1 * heat.shape[1]), max(6, 0.45 * heat.shape[0])))
        sns.heatmap(heat, cmap="GnBu", ax=ax, cbar_kws={"label": "% de los registros de la especie"})
        ax.set(title="Frecuencia relativa especie × hábitat", xlabel="Hábitat registrado", ylabel="Especie")
        for path in save_figure(fig, figure_dir / "Figure_09_06_Species_Habitat_Heatmap"):
            registry.add(path, "9", "Mapa de calor de especies por hábitat")

    depth_valid = table.dropna(subset=["Depth"]).copy()
    if not depth_valid.empty:
        fig, ax = plt.subplots(figsize=(9, 5.5))
        sns.histplot(depth_valid["Depth"], bins="auto", color="#2878b5", ax=ax)
        ax.set(title="Distribución global de la profundidad observada", xlabel="Profundidad (m)", ylabel="Registros")
        for path in save_figure(fig, figure_dir / "Figure_Depth_Overall_Histogram"):
            registry.add(path, "8.14", "Histograma global de profundidad")

        if depth_valid["Depth"].nunique() > 1:
            fig, ax = plt.subplots(figsize=(9, 5.5))
            sns.kdeplot(data=depth_valid, x="Depth", fill=True, color="#2a9d8f", ax=ax)
            ax.set(title="Densidad de la profundidad observada", xlabel="Profundidad (m)", ylabel="Densidad")
            for path in save_figure(fig, figure_dir / "Figure_Depth_Overall_Density"):
                registry.add(path, "8.14", "Densidad global de profundidad")

        class_counts = depth_valid["depth_class"].value_counts(sort=False).rename_axis("depth_class").reset_index(name="n_records")
        fig, ax = plt.subplots(figsize=(9, 5.5))
        sns.barplot(data=class_counts, x="depth_class", y="n_records", color="#e9c46a", ax=ax)
        ax.tick_params(axis="x", rotation=30)
        ax.set(title="Frecuencia por clase batimétrica", xlabel="Clase", ylabel="Registros")
        for path in save_figure(fig, figure_dir / "Figure_Depth_Bathymetric_Classes"):
            registry.add(path, "8.14", "Clases batimétricas")

        annual_depth_plot = depth_year.dropna(subset=["year", "depth_median"])
        if len(annual_depth_plot) >= 2:
            fig, ax = plt.subplots(figsize=(10, 5.5))
            sns.lineplot(data=annual_depth_plot, x="year", y="depth_median", marker="o", color="#6a4c93", ax=ax)
            ax.fill_between(annual_depth_plot["year"].astype(float), annual_depth_plot["depth_q25"].astype(float), annual_depth_plot["depth_q75"].astype(float), alpha=.18, color="#6a4c93")
            ax.set(title="Tendencia anual de la profundidad observada", xlabel="Año", ylabel="Profundidad mediana (m)")
            for path in save_figure(fig, figure_dir / "Figure_Depth_Annual_Trend"):
                registry.add(path, "8.14", "Tendencia anual de la profundidad")

        if depth_valid["abundance_aux"].notna().sum() >= 3:
            fig, ax = plt.subplots(figsize=(8, 5.5))
            sns.regplot(data=depth_valid, x="Depth", y="abundance_aux", scatter_kws={"alpha": .35, "s": 18}, line_kws={"color": "#d1495b"}, ax=ax)
            ax.set(title="Profundidad observada y abundancia", xlabel="Profundidad (m)", ylabel="N total")
            for path in save_figure(fig, figure_dir / "Figure_Depth_vs_Total_Abundance"):
                registry.add(path, "8.14", "Profundidad frente a abundancia")

    habitat_valid = table.dropna(subset=["Habitat_clean"]).copy()
    if not habitat_valid.empty:
        habitat_counts = habitat_valid["Habitat_clean"].value_counts().rename_axis("Habitat_clean").reset_index(name="n_records")
        habitat_counts["Habitat_clean"] = habitat_counts["Habitat_clean"].map(translate_habitat_value)
        fig, ax = plt.subplots(figsize=(10, max(5.5, .35 * len(habitat_counts))))
        sns.barplot(data=habitat_counts, x="n_records", y="Habitat_clean", color="#52b788", ax=ax)
        ax.set(title="Frecuencia de los hábitats observados", xlabel="Registros", ylabel="Hábitat")
        for path in save_figure(fig, figure_dir / "Figure_Habitat_Frequency"):
            registry.add(path, "8.14", "Frecuencia de hábitats")

        habitat_depth_valid = habitat_valid.dropna(subset=["Depth"])
        if not habitat_depth_valid.empty:
            habitat_depth_valid = habitat_depth_valid.copy()
            habitat_depth_valid["Habitat_clean"] = habitat_depth_valid["Habitat_clean"].map(translate_habitat_value)
            fig, ax = plt.subplots(figsize=(11, max(6, .4 * habitat_depth_valid["Habitat_clean"].nunique())))
            sns.boxplot(data=habitat_depth_valid, x="Depth", y="Habitat_clean", showfliers=False, color="#90be6d", ax=ax)
            ax.set(title="Profundidad por hábitat", xlabel="Profundidad (m)", ylabel="Hábitat")
            for path in save_figure(fig, figure_dir / "Figure_Depth_by_Habitat_Boxplot"):
                registry.add(path, "8.14", "Profundidad por hábitat")

            fig, ax = plt.subplots(figsize=(12, max(7, .45 * habitat_depth_valid["Species"].nunique())))
            species_present = set(habitat_depth_valid["Species"].astype(str))
            habitat_species_order = [sp for sp in depth_species_order if sp in species_present]
            sns.boxplot(
                data=habitat_depth_valid,
                x="Depth",
                y="Species",
                hue="Habitat_clean",
                order=habitat_species_order or None,
                showfliers=False,
                ax=ax,
            )
            ax.set(title="Profundidad y hábitat por especie", xlabel="Profundidad (m)", ylabel="Especie")
            ax.legend(title="Hábitat", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=7)
            for path in save_figure(fig, figure_dir / "Figure_Depth_Habitat_by_Species_Boxplot"):
                registry.add(path, "8.14", "Profundidad y hábitat por especie")

    LOGGER.info("    [1/8 · 4/4] Tablas y figuras descriptivas completadas")
    return {
        "observation_table": table,
        "effort_year": effort,
        "region_summary": region_summary,
        "species_global": species_global,
        "dominance": dominance,
        "habitat": habitat,
        "dominant_habitat": dominant_habitat,
        "community_region": community_region,
        "coast_distance": coast_distance,
        "coastal_occupancy": coastal_occupancy,
        "depth_species": depth_species,
        "depth_region": depth_region,
        "depth_year": depth_year,
        "depth_tests": depth_tests,
        "completeness": completeness,
    }
