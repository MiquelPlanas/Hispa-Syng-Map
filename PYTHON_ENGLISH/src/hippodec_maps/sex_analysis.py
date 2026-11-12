"""Global, regional, temporal, and spatial sex-composition analysis."""

from __future__ import annotations

from pathlib import Path
import logging
from typing import Any

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import statsmodels.api as sm
from scipy import stats

from .analysis_io import OutputRegistry, csv2, excel_book, save_figure, table_pair, text_file
from .localization import translate_geodataframe

LOGGER = logging.getLogger("hippodec_maps")


def _summary(table: pd.DataFrame, groups: list[str]) -> pd.DataFrame:
    grouped = (
        table.groupby(groups, dropna=False, observed=True)
        .agg(
            n_records=("grid_id", "size"),
            females=("female", "sum"),
            males=("male", "sum"),
            indeterminate=("indeterminate", "sum"),
        )
        .reset_index()
    )
    grouped["sexed"] = grouped["females"] + grouped["males"]
    grouped["female_proportion"] = grouped["females"] / grouped["sexed"].replace(0, np.nan)
    grouped["female_male_ratio"] = grouped["females"] / grouped["males"].replace(0, np.nan)
    grouped["sexual_bias"] = (grouped["females"] - grouped["males"]) / grouped["sexed"].replace(0, np.nan)
    p_values: list[float] = []
    ci_low: list[float] = []
    ci_high: list[float] = []
    for _, row in grouped.iterrows():
        if row["sexed"] > 0:
            result = stats.binomtest(int(row["females"]), int(row["sexed"]), p=0.5)
            interval = result.proportion_ci(confidence_level=0.95, method="exact")
            p_values.append(float(result.pvalue))
            ci_low.append(float(interval.low))
            ci_high.append(float(interval.high))
        else:
            p_values.append(np.nan)
            ci_low.append(np.nan)
            ci_high.append(np.nan)
    grouped["binomial_p_value_1to1"] = p_values
    grouped["female_proportion_ci_low"] = ci_low
    grouped["female_proportion_ci_high"] = ci_high
    return grouped


def run_sex_analysis(
    assigned: gpd.GeoDataFrame,
    occupied_cells: gpd.GeoDataFrame,
    directories: dict[str, Path],
    registry: OutputRegistry,
    selected_grid_km: int = 10,
) -> dict[str, Any]:
    LOGGER.info("    [5/8 · 1/3] Preparing sex-count data")
    table = pd.DataFrame(assigned.drop(columns="geometry")).copy()
    table["grid_id"] = table["grid_id"].astype(str)
    table["year"] = pd.to_datetime(table["Fecha_aux"], errors="coerce").dt.year.astype("Int64")
    table["female"] = pd.to_numeric(table["N hembra"], errors="coerce").fillna(0).clip(lower=0)
    table["male"] = pd.to_numeric(table["N macho"], errors="coerce").fillna(0).clip(lower=0)
    table["indeterminate"] = pd.to_numeric(table["N_indeterminado"], errors="coerce").fillna(0).clip(lower=0)
    table = table[(table[["female", "male", "indeterminate"]].sum(axis=1) > 0)].copy()
    if table.empty:
        registry.skip("12-sex", "Sex analysis", "There are no individuals with recorded sex")
        return {"available": False}

    LOGGER.info("    [5/8 · 2/3] Summaries, tests, and regional models")
    global_species = _summary(table, ["Species"])
    regional_species = _summary(table, ["Region_MITECO", "Species"])
    annual_species = _summary(table.dropna(subset=["year"]), ["year", "Species"])
    cell_species = _summary(table, ["grid_id", "Region_MITECO", "Species"])
    global_total = _summary(table.assign(scope="Global"), ["scope"])
    chi_rows: list[dict[str, Any]] = []
    residual_rows: list[dict[str, Any]] = []
    for species, subset in regional_species.groupby("Species", observed=True):
        contingency = subset.set_index("Region_MITECO")[["females", "males"]]
        contingency = contingency.loc[contingency.sum(axis=1) > 0]
        if contingency.shape[0] >= 2 and (contingency.sum(axis=0) > 0).all():
            observed = contingency.to_numpy(dtype=float, na_value=np.nan)
            observed = np.nan_to_num(observed, nan=0.0)
            chi2, p_value, dof, expected = stats.chi2_contingency(observed)
            chi_rows.append({"Species": species, "chi2": chi2, "df": dof, "p_value": p_value, "n_regions": len(contingency), "n_sexed": int(contingency.to_numpy().sum())})
            residuals = (contingency.to_numpy() - expected) / np.sqrt(expected)
            for region_index, region in enumerate(contingency.index):
                for sex_index, sex in enumerate(("females", "males")):
                    residual_rows.append({"Species": species, "Region_MITECO": region, "sex": sex, "standardized_residual": residuals[region_index, sex_index]})
        else:
            chi_rows.append({"Species": species, "chi2": np.nan, "df": np.nan, "p_value": np.nan, "n_regions": len(contingency), "n_sexed": int(contingency.to_numpy().sum())})
    regional_chi = pd.DataFrame(chi_rows)
    regional_residuals = pd.DataFrame(residual_rows)
    glm_rows: list[dict[str, Any]] = []
    model_input = table.assign(sexed=table["female"] + table["male"])
    model_input["female_proportion"] = model_input["female"] / model_input["sexed"].replace(0, np.nan)
    for species, subset in model_input.groupby("Species", observed=True):
        subset = subset[subset["sexed"].gt(0)].dropna(subset=["female_proportion", "Region_MITECO"]).copy()
        if len(subset) < 4 or subset["Region_MITECO"].nunique() < 2:
            glm_rows.append({"Species": species, "term": "model", "status": "insufficient_data"})
            continue
        try:
            design = pd.get_dummies(
                subset["Region_MITECO"].astype(str), prefix="Region_MITECO", drop_first=True, dtype=float
            )
            design = sm.add_constant(design, has_constant="add")
            if len(subset) <= design.shape[1]:
                raise ValueError("insufficient_residual_degrees_of_freedom")
            model = sm.GLM(
                subset["female_proportion"].astype(float), design,
                family=sm.families.Binomial(),
                freq_weights=subset["sexed"].astype(float),
            ).fit(scale="X2")
            for term in model.params.index:
                glm_rows.append({
                    "Species": species, "term": term, "estimate": model.params[term],
                    "std_error_quasi": model.bse[term], "z_value": model.tvalues[term],
                    "p_value": model.pvalues[term], "dispersion_pearson": model.scale,
                    "n_regions": subset["Region_MITECO"].nunique(), "n_records": len(subset), "n_sexed": subset["sexed"].sum(),
                    "status": "ok",
                })
        except Exception as exc:
            glm_rows.append({"Species": species, "term": "model", "status": f"failed: {type(exc).__name__}"})
    regional_glm = pd.DataFrame(glm_rows)

    LOGGER.info("    [5/8 · 3/3] Exporting sex tables, maps, and figures")
    tables = {
        "Global": global_total,
        "Species": global_species,
        "Region_species": regional_species,
        "Year_species": annual_species,
        "Cell_species": cell_species,
        "Chi2_region_species": regional_chi,
        "Chi2_residuals": regional_residuals,
        "Quasibinomial_GLM_region": regional_glm,
    }
    book = excel_book(tables, directories["04_tablas"] / "sex" / "Tables_Sex_Composition.xlsx")
    registry.add(book, "12-sex", "Sex-composition workbook")
    for name, frame in tables.items():
        path = csv2(frame, directories["04_tablas"] / "sex" / f"Table_Sex_{name}.csv")
        registry.add(path, "12-sex", f"Sex composition: {name}")
    resolution_tables = {
        f"Sex_by_MITECO_region_and_species_{selected_grid_km}km": regional_species,
        f"Global_coastal_sex_by_species_{selected_grid_km}km": global_species,
        f"Overall_global_coastal_sex_{selected_grid_km}km": global_total,
        f"Global_binomial_analysis_by_species_{selected_grid_km}km": global_species,
        f"MITECO_chi2_analysis_by_species_{selected_grid_km}km": regional_chi,
        f"MITECO_chi2_standardised_residuals_{selected_grid_km}km": regional_residuals,
        f"MITECO_quasibinomial_glm_analysis_{selected_grid_km}km": regional_glm,
    }
    for name, frame in resolution_tables.items():
        path = csv2(frame, directories["04_tablas"] / "sex" / f"{name}.csv")
        registry.add(path, "12-sex", f"Sex output for selected resolution: {name}")
    summary_resolution = excel_book(
        {"region_species": regional_species, "global_species": global_species,
         "global_total": global_total, "binomial": global_species, "chi2": regional_chi,
         "residuals": regional_residuals, "quasibinomial_glm": regional_glm},
        directories["04_tablas"] / "sex" / f"MITECO_and_Global_Sex_Summary_{selected_grid_km}km.xlsx",
    )
    registry.add(summary_resolution, "12-sex", "Sex workbook for the selected resolution")

    note = (
        "SEX COMPOSITION\n"
        "The female proportion is calculated among sexed individuals (females + males); indeterminate individuals are reported but excluded from the ratio.\n"
        "The two-sided binomial test evaluates an expected 1:1 proportion and is accompanied by an exact 95% interval.\n"
        "Results based on few sexed individuals are unstable and must be interpreted cautiously.\n"
    )
    note_path = text_file(note, directories["06_modelos"] / "sex" / "Methodological_Note_Sex_Composition.txt")
    registry.add(note_path, "12-sex", "Sex-composition methodological note")
    statistical_note = text_file(
        note + "The quasibinomial GLM uses aggregated individual records through frequency weights and Pearson scaling.\n",
        directories["06_modelos"] / "sex" / f"Statistical_Sex_Summary_{selected_grid_km}km.txt",
    )
    registry.add(statistical_note, "12-sex", "Statistical sex summary by resolution")

    fig, ax = plt.subplots(figsize=(9, max(6, 0.45 * len(global_species))))
    plot = global_species.sort_values("female_proportion")
    sns.barplot(data=plot, x="female_proportion", y="Species", color="#d95f9f", ax=ax)
    ax.axvline(0.5, color="black", linestyle="--", linewidth=1)
    ax.set(xlim=(0, 1), xlabel="Female proportion among sexed individuals", ylabel="Species", title="Sex composition by species")
    for path in save_figure(fig, directories["05_figuras"] / "sex" / "Figure_Sex_Composition_by_Species"):
        registry.add(path, "12-sex", "Sex-composition figure by species")

    geometry = occupied_cells[["grid_id", "geometry"]].drop_duplicates("grid_id").copy()
    geometry["grid_id"] = geometry["grid_id"].astype(str)
    cell_global = _summary(table, ["grid_id"])
    spatial = geometry.merge(cell_global, on="grid_id", how="inner")
    spatial = gpd.GeoDataFrame(spatial, geometry="geometry", crs=occupied_cells.crs)
    gpkg = directories["02_intermedios"] / "Cell_Sex_Composition.gpkg"
    translate_geodataframe(spatial).to_file(gpkg, layer="cell_sex_composition", driver="GPKG", engine="pyogrio")
    registry.add(gpkg, "12-sex", "Sex-composition GeoPackage by cell")

    return {
        "available": True,
        "global": global_total,
        "species": global_species,
        "region_species": regional_species,
        "year_species": annual_species,
        "cell_species": cell_species,
        "spatial": spatial,
    }
