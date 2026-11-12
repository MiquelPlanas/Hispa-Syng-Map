"""Calculation of cartographic metrics by cell and species."""

from __future__ import annotations

import math

import geopandas as gpd
import numpy as np
import pandas as pd


def _quality_label(value: float) -> str:
    if value >= 0.75:
        return "Alta"
    if value >= 0.50:
        return "Media"
    if value >= 0.25:
        return "Baja"
    return "Muy baja"


def calculate_metrics(
    assigned: gpd.GeoDataFrame,
    grid: gpd.GeoDataFrame,
    resolution_km: int,
) -> tuple[
    gpd.GeoDataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]
]:
    table = pd.DataFrame(assigned.drop(columns="geometry")).copy()
    table["N_total"] = pd.to_numeric(table["N_total"], errors="coerce")
    table["N_for_sum"] = table["N_total"].fillna(0)
    table["year"] = pd.to_datetime(table["Fecha_aux"], errors="coerce").dt.year
    table["Area_mar_km2"] = pd.to_numeric(table["Area_mar_km2"], errors="coerce")
    invalid_area = table["Area_mar_km2"].isna() | table["Area_mar_km2"].le(0)
    if invalid_area.any():
        affected = table.loc[invalid_area, "grid_id"].dropna().astype(str).unique()
        raise ValueError(
            "Densities cannot be calculated: occupied cells lack a validated positive marine surface: "
            + ", ".join(affected[:10])
        )
    if "Area_celda_km2" in table:
        full_area = pd.to_numeric(table["Area_celda_km2"], errors="coerce")
        exceeds_cell = table["Area_mar_km2"].gt(
            np.maximum(full_area * 1.0000001, full_area + 1e-8)
        )
        if exceeds_cell.any():
            raise AssertionError(
                "The clipped marine surface exceeds the geometric cell surface."
            )
    if "Area_mar_source" in table:
        valid_sources = {"gshhs_clipped_geometry", "miteco_demarcation_fallback_geometry"}
        invalid_source = ~table["Area_mar_source"].astype("string").isin(valid_sources)
        if invalid_source.any():
            raise AssertionError(
                "Density may only use a validated marine geometry from GSHHS or, when GSHHS produces a coastal false zero, from the official MITECO marine demarcation."
            )

    cell = (
        table.groupby(["grid_id", "Area_mar_km2"], dropna=False)
        .agg(
            N_total_celda=("N_for_sum", "sum"),
            n_especies=("Species", "nunique"),
            n_obs_cell=("obs_id", "size"),
            n_years_cell=("year", "nunique"),
            dist_mean=("dist_to_cell_m", "mean"),
        )
        .reset_index()
    )
    cell["Densidad_total"] = np.where(
        cell["Area_mar_km2"].gt(0),
        cell["N_total_celda"] / cell["Area_mar_km2"],
        np.nan,
    )
    max_log_n = float(np.log1p(cell["n_obs_cell"]).max()) if not cell.empty else 0.0
    cell["Q_n"] = np.log1p(cell["n_obs_cell"]) / max_log_n if max_log_n > 0 else 0.0
    tolerance = resolution_km * 1000.0
    cell["Q_dist"] = np.maximum(
        0.0, 1.0 - cell["dist_mean"].fillna(tolerance) / tolerance
    )
    cell["Q_total"] = 0.6 * cell["Q_n"] + 0.4 * cell["Q_dist"]
    cell["calidad"] = cell["Q_total"].map(_quality_label)

    species = (
        table.groupby(["grid_id", "Species", "Area_mar_km2"], dropna=False)["N_for_sum"]
        .sum()
        .rename("N_sum")
        .reset_index()
    )
    species["Densidad_ajustada"] = np.where(
        species["Area_mar_km2"].gt(0),
        species["N_sum"] / species["Area_mar_km2"],
        np.nan,
    )
    species["N_total_celda"] = species.groupby("grid_id")["N_sum"].transform("sum")
    species["pct_rel"] = np.where(
        species["N_total_celda"].gt(0),
        species["N_sum"] / species["N_total_celda"] * 100,
        0.0,
    )
    dominant = (
        species.sort_values(
            ["grid_id", "N_sum", "Species"], ascending=[True, False, True]
        )
        .drop_duplicates("grid_id")[["grid_id", "Species", "N_sum"]]
        .rename(columns={"Species": "Species_dom", "N_sum": "N_sum_dom"})
    )
    cell = cell.merge(dominant, on="grid_id", how="left")

    for column in ("N hembra", "N macho", "N_indeterminado"):
        table[column] = pd.to_numeric(table[column], errors="coerce").fillna(0)
    sex = (
        table.groupby(["grid_id", "Region_MITECO", "Species"], dropna=False)
        .agg(
            N_hembras=("N hembra", "sum"),
            N_machos=("N macho", "sum"),
            N_indeterminados=("N_indeterminado", "sum"),
        )
        .reset_index()
    )
    sex["N_sexados"] = sex["N_hembras"] + sex["N_machos"]
    sex["ratio_HM"] = np.where(
        sex["N_machos"].gt(0), sex["N_hembras"] / sex["N_machos"], np.nan
    )
    sex["prop_hembras"] = np.where(
        sex["N_sexados"].gt(0), sex["N_hembras"] / sex["N_sexados"], np.nan
    )
    sex["sesgo_sexual"] = np.where(
        sex["N_sexados"].gt(0),
        (sex["N_hembras"] - sex["N_machos"]) / sex["N_sexados"],
        np.nan,
    )
    sex = sex[sex["N_sexados"].gt(0)].copy()

    occupied = grid.merge(cell, on=["grid_id", "Area_mar_km2"], how="inner")
    occupied = gpd.GeoDataFrame(occupied, geometry="geometry", crs=grid.crs)

    assigned_abundance = float(table["N_for_sum"].sum())
    cell_abundance = float(cell["N_total_celda"].sum())
    if not math.isclose(
        assigned_abundance, cell_abundance, rel_tol=1e-12, abs_tol=1e-9
    ):
        raise AssertionError(
            "Total abundance differs before and after aggregation by cell."
        )
    if not set(occupied["grid_id"]).issubset(set(grid["grid_id"])):
        raise AssertionError(
            "Some occupied cells have grid_id values that do not exist in the grid."
        )
    expected_cell_density = cell["N_total_celda"] / cell["Area_mar_km2"]
    if not np.allclose(
        cell["Densidad_total"], expected_cell_density, rtol=1e-12, atol=1e-9
    ):
        raise AssertionError(
            "Total density does not equal N / validated marine surface."
        )
    expected_species_density = species["N_sum"] / species["Area_mar_km2"]
    if not np.allclose(
        species["Densidad_ajustada"],
        expected_species_density,
        rtol=1e-12,
        atol=1e-9,
    ):
        raise AssertionError(
            "Species density does not equal N / validated marine surface."
        )
    area_source_counts = (
        {
            str(key): int(value)
            for key, value in table["Area_mar_source"].value_counts(
                dropna=False
            ).items()
        }
        if "Area_mar_source" in table
        else {}
    )
    qa = {
        "occupied_cells": int(len(occupied)),
        "total_abundance_assigned": assigned_abundance,
        "total_abundance_cells": cell_abundance,
        "species_cell_rows": int(len(species)),
        "sex_cell_species_rows": int(len(sex)),
        "density_denominator": "marine_geometry_km2_gshhs_primary_miteco_fallback",
        "density_scale_km2": 1,
        "density_formula_verified": True,
        "density_land_excluded": True,
        "occupied_area_source_counts": area_source_counts,
    }
    return occupied, cell, species, sex, qa
