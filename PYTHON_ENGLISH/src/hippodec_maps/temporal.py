"""Block 20: trends, periods, spatial changes, and narrative."""

from __future__ import annotations

import json
import logging
import math
import warnings
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import statsmodels.api as sm
from statsmodels.tools.sm_exceptions import ConvergenceWarning, HessianInversionWarning, PerfectSeparationWarning
from matplotlib.patches import Patch
from scipy import stats
from shapely.geometry import box
from sklearn.preprocessing import SplineTransformer

LOGGER = logging.getLogger("hippodec_maps")

from .analysis_io import (
    OutputRegistry,
    csv2,
    excel_book,
    finite_quantile,
    mode_or_na,
    save_figure,
    table_pair,
    text_file,
)
from .analysis_utils import AnalysisSettings, rescale
from .config import ascii_slug, taxon_slug
from .cartography import MapContext, add_map_context
from .localization import translate_geodataframe, translate_text


@dataclass(frozen=True)
class Period:
    label: str
    start: pd.Timestamp
    end: pd.Timestamp
    requested_start: pd.Timestamp | None = None
    requested_end: pd.Timestamp | None = None


def _periods(table: pd.DataFrame, settings: AnalysisSettings) -> list[Period]:
    minimum = pd.to_datetime(table["Fecha_aux"]).min().normalize()
    maximum = pd.to_datetime(
        table["Fecha_aux"]
    ).max().normalize() + pd.offsets.MonthEnd(0)
    result: list[Period] = []
    if not settings.temporal_periods:
        return [
            Period(
                f"Overall period {minimum.year}–{maximum.year}",
                minimum,
                maximum,
                minimum,
                maximum,
            )
        ]
    for label, start, end in settings.temporal_periods:
        requested_left = pd.Timestamp(start).normalize()
        requested_right = pd.Timestamp(end).normalize() + pd.offsets.MonthEnd(0)
        if requested_left > requested_right:
            raise ValueError(f"Temporal period {label!r} starts after it ends.")
        left, right = max(requested_left, minimum), min(requested_right, maximum)
        if left <= right:
            result.append(
                Period(label, left, right, requested_left, requested_right)
            )
    if len(result) < 2:
        raise ValueError(
            "The selected comparison periods do not provide at least two valid intervals within the analysed data."
        )
    if len({period.label for period in result}) != len(result):
        raise ValueError("Temporal period labels must be unique.")
    ordered = sorted(result, key=lambda period: period.start)
    if any(current.start <= previous.end for previous, current in zip(ordered, ordered[1:])):
        raise ValueError("Temporal comparison periods must not overlap.")
    return result


def _assign_period(dates: pd.Series, periods: list[Period]) -> pd.Series:
    result = pd.Series(pd.NA, index=dates.index, dtype="string")
    for period in periods:
        result.loc[dates.between(period.start, period.end)] = period.label
    return result


def _figure_period_label(period: Period) -> str:
    """Compact period label for figures: calendar years only."""

    start = period.requested_start if period.requested_start is not None else period.start
    end = period.requested_end if period.requested_end is not None else period.end
    start_year, end_year = int(start.year), int(end.year)
    return str(start_year) if start_year == end_year else f"{start_year}–{end_year}"


def _figure_label_maps(periods: list[Period]) -> tuple[dict[str, str], dict[str, str]]:
    """Return compact display labels without changing analytical identifiers."""

    period_labels = {period.label: _figure_period_label(period) for period in periods}
    comparison_labels: dict[str, str] = {}
    for first, second in combinations(periods, 2):
        comparison_labels[f"{first.label} vs {second.label}"] = (
            f"{period_labels[first.label]} / {period_labels[second.label]}"
        )
    return period_labels, comparison_labels


def _duration_years(period: Period) -> float:
    """Return the effective calendar duration represented by a period."""

    return float((period.end - period.start).days + 1) / 365.2425


def _sum_distinct_cell_area(frame: pd.DataFrame) -> float:
    """Sum marine area once per official cell, never once per area value."""

    if frame.empty or "Area_mar_km2" not in frame:
        return float("nan")
    cells = frame[["grid_id", "Area_mar_km2"]].copy()
    cells["Area_mar_km2"] = pd.to_numeric(cells["Area_mar_km2"], errors="coerce")
    cells = cells.dropna(subset=["grid_id", "Area_mar_km2"])
    cells = cells[cells["Area_mar_km2"].gt(0)].drop_duplicates("grid_id")
    return float(cells["Area_mar_km2"].sum()) if not cells.empty else float("nan")


def _rescale01(values: pd.Series) -> pd.Series:
    """R-compatible 0-1 scaling that preserves missing values."""

    numeric = pd.to_numeric(values, errors="coerce")
    finite = numeric[np.isfinite(numeric)]
    if finite.empty:
        return pd.Series(np.nan, index=values.index, dtype=float)
    lower, upper = float(finite.min()), float(finite.max())
    if not np.isfinite(lower) or not np.isfinite(upper) or upper == lower:
        result = pd.Series(0.0, index=values.index, dtype=float)
        result.loc[numeric.isna()] = np.nan
        return result
    return (numeric - lower) / (upper - lower)



def _symmetric_relative_change(first: pd.Series, second: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Cambio simétrico no negativo y cambio firmado, invariantes a la unidad.

    Para valores no negativos usa ``|x2-x1|/(x1+x2)`` como magnitud y
    ``(x2-x1)/(x1+x2)`` como dirección. Si ambos valores son cero, ambos
    resultados son cero. Los pares no finitos permanecen como NA.
    """

    left = pd.to_numeric(first, errors="coerce").astype(float)
    right = pd.to_numeric(second, errors="coerce").astype(float)
    valid = np.isfinite(left) & np.isfinite(right) & left.ge(0) & right.ge(0)
    denominator = left + right
    magnitude = pd.Series(np.nan, index=left.index, dtype=float)
    signed = pd.Series(np.nan, index=left.index, dtype=float)
    both_zero = valid & denominator.eq(0)
    nonzero = valid & denominator.gt(0)
    magnitude.loc[both_zero] = 0.0
    signed.loc[both_zero] = 0.0
    magnitude.loc[nonzero] = (right.loc[nonzero] - left.loc[nonzero]).abs() / denominator.loc[nonzero]
    signed.loc[nonzero] = (right.loc[nonzero] - left.loc[nonzero]) / denominator.loc[nonzero]
    return magnitude, signed


def _temporal_inference_support(frame: pd.DataFrame) -> dict[str, Any]:
    """Evalúa si una especie tiene soporte mínimo para inferencia temporal."""

    detections = frame[pd.to_numeric(frame["abundance"], errors="coerce").fillna(0).gt(0)].copy()
    detection_years = sorted(detections["year"].dropna().astype(int).unique())
    n_detection_years = len(detection_years)
    detection_span_years = (
        int(max(detection_years) - min(detection_years) + 1) if detection_years else 0
    )
    n_detection_events = int(
        pd.to_numeric(detections.get("species_sampling_events", 0), errors="coerce").fillna(0).sum()
    )
    inferential = (
        n_detection_years >= 8
        and n_detection_events >= 20
        and detection_span_years >= 10
    )
    return {
        "n_detection_years": int(n_detection_years),
        "n_detection_events": int(n_detection_events),
        "detection_span_years": int(detection_span_years),
        "inference_scope": "inferential" if inferential else "descriptive_only",
        "support_reason": (
            "meets_minimum_temporal_support"
            if inferential
            else "requires_>=8_detection_years_>=20_detection_events_>=10_year_span"
        ),
    }

def _period_definition(table: pd.DataFrame, periods: list[Period]) -> pd.DataFrame:
    """Document requested/effective limits and incomplete end-period coverage."""

    rows: list[dict[str, Any]] = []
    for period in periods:
        subset = table[table["period"].eq(period.label)].copy()
        requested_start = (
            period.requested_start
            if period.requested_start is not None
            else period.start
        )
        requested_end = (
            period.requested_end if period.requested_end is not None else period.end
        )
        observed_start = subset["Fecha_aux"].min() if not subset.empty else pd.NaT
        observed_end = subset["Fecha_aux"].max() if not subset.empty else pd.NaT
        rows.append(
            {
                "period": period.label,
                "requested_start": requested_start.date().isoformat(),
                "requested_end": requested_end.date().isoformat(),
                "effective_start": period.start.date().isoformat(),
                "effective_end": period.end.date().isoformat(),
                "effective_duration_days": int((period.end - period.start).days + 1),
                "effective_duration_years": _duration_years(period),
                "n_records": int(len(subset)),
                "n_sampling_events": int(subset["sampling_event_id"].nunique()) if "sampling_event_id" in subset.columns else 0,
                "n_years_with_records": int(subset["year"].nunique()),
                "n_months_with_records": int(subset["Fecha_aux"].dt.to_period("M").nunique()),
                "first_observation": observed_start.date().isoformat() if pd.notna(observed_start) else pd.NA,
                "last_observation": observed_end.date().isoformat() if pd.notna(observed_end) else pd.NA,
                "clipped_at_data_start": bool(period.start > requested_start),
                "clipped_at_data_end": bool(period.end < requested_end),
                "requested_interval_fully_covered": bool(
                    period.start == requested_start and period.end == requested_end
                ),
            }
        )
    return pd.DataFrame(rows)


def _adjust_valid_pvalues(values: pd.Series) -> pd.Series:
    """Apply Benjamini-Hochberg only to calculable tests and retain NA."""

    result = pd.Series(np.nan, index=values.index, dtype=float)
    numeric = pd.to_numeric(values, errors="coerce")
    valid = numeric.notna() & np.isfinite(numeric)
    if valid.any():
        result.loc[valid] = stats.false_discovery_control(
            numeric.loc[valid].to_numpy(dtype=float), method="bh"
        )
    return result


def _safe_kruskal(first: pd.Series, second: pd.Series) -> tuple[float, float]:
    """Kruskal-Wallis on annual values, with explicit non-calculable cases."""

    left = pd.to_numeric(first, errors="coerce").dropna()
    right = pd.to_numeric(second, errors="coerce").dropna()
    if len(left) < 2 or len(right) < 2:
        return np.nan, np.nan
    combined = pd.concat([left, right], ignore_index=True)
    if combined.nunique(dropna=True) < 2:
        return np.nan, np.nan
    test = stats.kruskal(left.to_numpy(dtype=float), right.to_numpy(dtype=float))
    return float(test.statistic), float(test.pvalue)


def _annual(table: pd.DataFrame) -> pd.DataFrame:
    source = table.copy()
    if "sampling_event_id" not in source.columns:
        raise ValueError("sampling_event_id is missing from the temporal analysis.")
    source["Area_mar_km2"] = pd.to_numeric(source.get("Area_mar_km2"), errors="coerce")
    effort = source.groupby("year", observed=True).agg(
        effort_records=("grid_id", "size"),
        n_sampling_events=("sampling_event_id", "nunique"),
        sampled_cells=("grid_id", "nunique"),
        total_abundance=("N_aux", "sum"),
    ).reset_index()
    sampled_area = (
        source[["year", "grid_id", "Area_mar_km2"]]
        .dropna(subset=["grid_id", "Area_mar_km2"])
        .drop_duplicates(["year", "grid_id"])
        .groupby("year", observed=True)["Area_mar_km2"]
        .sum().rename("sampled_area_km2").reset_index()
    )
    calendar = source.groupby("year", observed=True)["Fecha_aux"].agg(
        first_observation="min", last_observation="max"
    ).reset_index()
    months = (
        source.assign(observed_month=source["Fecha_aux"].dt.to_period("M"))
        .groupby("year", observed=True)["observed_month"].nunique()
        .rename("months_with_records").reset_index()
    )
    effort = effort.merge(sampled_area, on="year", how="left").merge(
        calendar, on="year", how="left"
    ).merge(months, on="year", how="left")
    latest_year = int(source["year"].max())
    data_end = source["Fecha_aux"].max().normalize()
    effort["latest_data_year_incomplete"] = (
        effort["year"].eq(latest_year)
        & (data_end < pd.Timestamp(year=latest_year, month=12, day=31))
    )
    grouped = source.groupby(["Species", "year"], observed=True).agg(
        n_records=("grid_id", "size"),
        species_sampling_events=("sampling_event_id", "nunique"),
        abundance=("N_aux", "sum"),
        detected_cells=("grid_id", "nunique"),
        depth_median=("Depth_aux", "median"),
        habitat_dominant=("Habitat_aux", mode_or_na),
    ).reset_index()
    occupied_area = (
        source[["Species", "year", "grid_id", "Area_mar_km2"]]
        .dropna(subset=["grid_id", "Area_mar_km2"])
        .drop_duplicates(["Species", "year", "grid_id"])
        .groupby(["Species", "year"], observed=True)["Area_mar_km2"]
        .sum().rename("occupied_area_km2").reset_index()
    )
    grouped = grouped.merge(occupied_area, on=["Species", "year"], how="left")
    species = sorted(source["Species"].dropna().unique())
    years = sorted(source["year"].dropna().astype(int).unique())
    complete = pd.MultiIndex.from_product([species, years], names=["Species", "year"]).to_frame(index=False)
    complete = complete.merge(grouped, on=["Species", "year"], how="left").merge(effort, on="year", how="left")
    for column in ("n_records", "species_sampling_events", "abundance", "detected_cells"):
        complete[column] = pd.to_numeric(complete[column], errors="coerce").fillna(0)
    complete["occupied_cells"] = complete["detected_cells"]
    complete["occupied_area_km2"] = pd.to_numeric(complete["occupied_area_km2"], errors="coerce").fillna(0)
    complete["detection_frequency_sampled_cells_pct"] = (
        100 * complete["detected_cells"] / complete["sampled_cells"].replace(0, np.nan)
    )
    complete["occupancy_pct"] = complete["detection_frequency_sampled_cells_pct"]
    complete["abundance_per_sampling_event"] = (
        complete["abundance"] / complete["n_sampling_events"].replace(0, np.nan)
    )
    complete["abundance_per_100_sampling_events"] = 100 * complete["abundance_per_sampling_event"]
    # Sensibilidad/descriptivo legado: filas, no esfuerzo principal.
    complete["abundance_per_record_global"] = (
        complete["abundance"] / complete["effort_records"].replace(0, np.nan)
    )
    complete["abundance_per_100_records"] = 100 * complete["abundance_per_record_global"]
    complete["records_per_100_records"] = 100 * complete["n_records"] / complete["effort_records"].replace(0, np.nan)
    complete["abundance_per_sampled_cell"] = complete["abundance"] / complete["sampled_cells"].replace(0, np.nan)
    complete["density_occupied_area_km2"] = np.where(
        complete["occupied_area_km2"].gt(0),
        complete["abundance"] / complete["occupied_area_km2"],
        np.where(complete["abundance"].eq(0), 0.0, np.nan),
    )
    complete["density_sampled_area_km2"] = complete["abundance"] / complete["sampled_area_km2"].replace(0, np.nan)
    complete["observation_rate_norm"] = complete.groupby("Species", observed=True)["abundance_per_sampling_event"].transform(_rescale01)
    complete["detection_frequency_norm"] = complete.groupby("Species", observed=True)["detection_frequency_sampled_cells_pct"].transform(_rescale01)
    complete["annual_relative_observation_index"] = 0.5 * (
        complete["observation_rate_norm"] + complete["detection_frequency_norm"]
    )
    # Internal convenience fields; public interpretation uses recorded-detection terminology.
    complete["abundance_effort_norm"] = complete["observation_rate_norm"]
    complete["occupancy_norm"] = complete["detection_frequency_norm"]
    complete["annual_population_index"] = complete["annual_relative_observation_index"]
    return complete

def _annual_period_metrics(table: pd.DataFrame, periods: list[Period]) -> pd.DataFrame:
    """Creates independent species-year observations within each period."""

    source = table.dropna(subset=["period"]).copy()
    if "sampling_event_id" not in source.columns:
        raise ValueError("sampling_event_id is missing from the temporal analysis.")
    effort = source.groupby(["period", "year"], observed=True).agg(
        effort_records=("grid_id", "size"),
        n_sampling_events=("sampling_event_id", "nunique"),
        sampled_cells=("grid_id", "nunique"),
        total_abundance=("N_aux", "sum"),
    ).reset_index()
    sampled_area = (
        source[["period", "year", "grid_id", "Area_mar_km2"]]
        .drop_duplicates(["period", "year", "grid_id"])
        .groupby(["period", "year"], observed=True)["Area_mar_km2"]
        .sum().rename("sampled_area_km2").reset_index()
    )
    effort = effort.merge(sampled_area, on=["period", "year"], how="left")
    observed = source.groupby(["Species", "period", "year"], observed=True).agg(
        n_records=("grid_id", "size"),
        species_sampling_events=("sampling_event_id", "nunique"),
        abundance=("N_aux", "sum"),
        detected_cells=("grid_id", "nunique"),
    ).reset_index()
    occupied_area = (
        source[["Species", "period", "year", "grid_id", "Area_mar_km2"]]
        .drop_duplicates(["Species", "period", "year", "grid_id"])
        .groupby(["Species", "period", "year"], observed=True)["Area_mar_km2"]
        .sum().rename("occupied_area_km2").reset_index()
    )
    observed = observed.merge(occupied_area, on=["Species", "period", "year"], how="left")
    species = pd.DataFrame({"Species": sorted(source["Species"].dropna().unique())})
    sampled_period_years = effort[["period", "year"]].drop_duplicates()
    species["_cross"], sampled_period_years["_cross"] = 1, 1
    complete = species.merge(sampled_period_years, on="_cross").drop(columns="_cross")
    complete = complete.merge(observed, on=["Species", "period", "year"], how="left").merge(effort, on=["period", "year"], how="left")
    for column in ("n_records", "species_sampling_events", "abundance", "detected_cells", "occupied_area_km2"):
        complete[column] = pd.to_numeric(complete[column], errors="coerce").fillna(0)
    complete["occupied_cells"] = complete["detected_cells"]
    complete["abundance_per_sampling_event"] = complete["abundance"] / complete["n_sampling_events"].replace(0, np.nan)
    complete["abundance_per_record_global"] = complete["abundance"] / complete["effort_records"].replace(0, np.nan)
    complete["detection_frequency_sampled_cells"] = complete["detected_cells"] / complete["sampled_cells"].replace(0, np.nan)
    complete["occupancy_prop"] = complete["detection_frequency_sampled_cells"]
    complete["density_occupied_area_km2"] = np.where(
        complete["occupied_area_km2"].gt(0),
        complete["abundance"] / complete["occupied_area_km2"],
        np.where(complete["abundance"].eq(0), 0.0, np.nan),
    )
    complete["density_sampled_area_km2"] = complete["abundance"] / complete["sampled_area_km2"].replace(0, np.nan)
    complete["observation_rate_norm"] = complete.groupby("Species", observed=True)["abundance_per_sampling_event"].transform(_rescale01)
    complete["detection_frequency_norm"] = complete.groupby("Species", observed=True)["detection_frequency_sampled_cells"].transform(_rescale01)
    complete["annual_relative_observation_index"] = 0.5 * (complete["observation_rate_norm"] + complete["detection_frequency_norm"])
    complete["abundance_effort_norm"] = complete["observation_rate_norm"]
    complete["occupancy_norm"] = complete["detection_frequency_norm"]
    complete["annual_population_index"] = complete["annual_relative_observation_index"]
    period_order = {period.label: index for index, period in enumerate(periods)}
    complete["_period_order"] = complete["period"].map(period_order)
    return complete.sort_values(["Species", "_period_order", "year"]).drop(columns="_period_order").reset_index(drop=True)

def _fit_models(annual: pd.DataFrame, settings: AnalysisSettings) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fits the conservative primary temporal trend and species-level sensitivities.

    Primary model: Poisson with log(n_sampling_events) offset and covariance
    scaled by Pearson overdispersion, with a minimum phi of 1. NB2 is retained
    only as a sensitivity analysis when inferential support is sufficient.
    """

    model_rows: list[dict[str, Any]] = []
    predictions: list[pd.DataFrame] = []
    for _, (species, frame) in enumerate(annual.groupby("Species", observed=True)):
        frame = frame.sort_values("year").copy()
        usable = frame[(frame["n_sampling_events"] > 0) & frame["year"].notna()].copy()
        support = _temporal_inference_support(usable)
        common = {"Species": species, **support, "n_years_sampled": int(usable["year"].nunique()), "n_years": int(usable["year"].nunique())}
        if support["inference_scope"] != "inferential" or len(usable) < 4:
            model_rows.append({
                **common,
                "model": "Poisson-Pearson observation-rate trend",
                "status": "descriptive_only",
                "analysis_status": "insufficient_data",
            })
            continue

        event_rate = usable["abundance"] / usable["n_sampling_events"].replace(0, np.nan)
        if event_rate.dropna().nunique() < 2:
            model_rows.append({
                **common,
                "model": "Poisson-Pearson observation-rate trend",
                "status": "descriptive_only",
                "analysis_status": "not_estimable",
                "support_reason": "constant_observation_rate_no_inferential_variation",
            })
            continue
        centered = usable["year"].astype(float) - usable["year"].mean()
        design = sm.add_constant(centered.to_numpy())
        prediction_frame: pd.DataFrame | None = None
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", PerfectSeparationWarning)
                glm = sm.GLM(
                    usable["abundance"].to_numpy(dtype=float),
                    design,
                    family=sm.families.Poisson(),
                    offset=np.log(usable["n_sampling_events"].to_numpy(dtype=float)),
                ).fit()
            slope = float(glm.params[1])
            phi_raw = float(glm.pearson_chi2 / glm.df_resid) if glm.df_resid > 0 else 1.0
            phi = max(1.0, phi_raw) if np.isfinite(phi_raw) else 1.0
            covariance = np.asarray(glm.cov_params(), dtype=float) * phi
            slope_se = float(np.sqrt(max(covariance[1, 1], 0.0)))
            z_value = slope / slope_se if slope_se > 0 else np.nan
            p_value = float(2 * stats.norm.sf(abs(z_value))) if np.isfinite(z_value) else np.nan
            slope_ci_low = slope - 1.96 * slope_se if np.isfinite(slope_se) else np.nan
            slope_ci_high = slope + 1.96 * slope_se if np.isfinite(slope_se) else np.nan
            model_rows.append({
                **common,
                "model": "Poisson-Pearson observation-rate trend",
                "status": "ok",
                "analysis_status": "calculable",
                "slope_log_rate_per_year": slope,
                "slope_log_per_year": slope,
                "slope_se_pearson": slope_se,
                "slope_ci_low": slope_ci_low,
                "slope_ci_high": slope_ci_high,
                "annual_change_pct": 100 * (math.exp(slope) - 1),
                "annual_change_ci_low_pct": 100 * (math.exp(slope_ci_low) - 1) if np.isfinite(slope_ci_low) else np.nan,
                "annual_change_ci_high_pct": 100 * (math.exp(slope_ci_high) - 1) if np.isfinite(slope_ci_high) else np.nan,
                "p_value": p_value,
                "pearson_dispersion_raw": phi_raw,
                "pearson_dispersion_used": phi,
                "poisson_AIC_unscaled": float(glm.aic),
                "AIC": float(glm.aic),
                "aic_basis": "unscaled_poisson_likelihood_not_quasi_inference",
                "deviance": float(glm.deviance),
                "offset_variable": "n_sampling_events",
            })
            linear_predictor = design @ glm.params
            standard_error = np.sqrt(np.einsum("ij,jk,ik->i", design, covariance, design))
            rate = np.exp(linear_predictor)
            prediction_frame = pd.DataFrame({
                "Species": species,
                "year": usable["year"].to_numpy(dtype=int),
                "glm_predicted_abundance_per_sampling_event": rate,
                "glm_predicted_abundance_per_100_sampling_events": 100 * rate,
                "glm_ci_low_per_sampling_event": np.exp(linear_predictor - 1.96 * standard_error),
                "glm_ci_high_per_sampling_event": np.exp(linear_predictor + 1.96 * standard_error),
            })
        except Exception as exc:
            model_rows.append({
                **common,
                "model": "Poisson-Pearson observation-rate trend",
                "status": f"failed: {type(exc).__name__}",
                "analysis_status": "not_estimable",
            })

        # NB2: sensibilidad solamente; no sustituye la inferencia principal.
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", RuntimeWarning)
                warnings.simplefilter("error", ConvergenceWarning)
                warnings.simplefilter("error", HessianInversionWarning)
                warnings.simplefilter("error", PerfectSeparationWarning)
                nb = sm.NegativeBinomial(
                    usable["abundance"].to_numpy(dtype=float),
                    design,
                    loglike_method="nb2",
                    offset=np.log(usable["n_sampling_events"].to_numpy(dtype=float)),
                ).fit(disp=0, maxiter=250)
            converged = bool(getattr(nb, "mle_retvals", {}).get("converged", True))
            alpha = float(nb.params[-1]) if len(nb.params) > design.shape[1] else np.nan
            nb_slope = float(nb.params[1])
            nb_p = float(nb.pvalues[1]) if len(nb.pvalues) > 1 else np.nan
            valid = converged and np.isfinite(nb_slope) and np.isfinite(alpha) and alpha >= 0
            model_rows.append({
                **common,
                "model": "NB2 sensitivity",
                "status": "ok" if valid else "not_estimable",
                "analysis_status": "calculable" if valid else "not_estimable",
                "slope_log_rate_per_year": nb_slope if valid else np.nan,
                "annual_change_pct": 100 * (math.exp(nb_slope) - 1) if valid else np.nan,
                "p_value": nb_p if valid else np.nan,
                "alpha_nb2": alpha,
                "converged": converged,
                "AIC": float(nb.aic) if valid else np.nan,
                "offset_variable": "n_sampling_events",
            })
        except Exception as exc:
            model_rows.append({
                **common,
                "model": "NB2 sensitivity",
                "status": f"failed: {type(exc).__name__}",
                "analysis_status": "not_estimable",
                "offset_variable": "n_sampling_events",
            })

        # Curva flexible descriptiva sobre conteos originales + offset de eventos.
        try:
            x = usable[["year"]].to_numpy(dtype=float)
            knots = min(5, max(3, len(usable) // 3))
            spline = SplineTransformer(n_knots=knots, degree=3, include_bias=False)
            basis = spline.fit_transform(x)
            design_spline = sm.add_constant(basis, has_constant="add")
            with warnings.catch_warnings():
                warnings.simplefilter("error", PerfectSeparationWarning)
                spline_fit = sm.GLM(
                    usable["abundance"].to_numpy(dtype=float),
                    design_spline,
                    family=sm.families.Poisson(),
                    offset=np.log(usable["n_sampling_events"].to_numpy(dtype=float)),
                ).fit()
            years = np.arange(int(usable["year"].min()), int(usable["year"].max()) + 1)
            basis_pred = spline.transform(years.reshape(-1, 1))
            design_pred = sm.add_constant(basis_pred, has_constant="add")
            predicted_rate = np.clip(np.exp(design_pred @ spline_fit.params), 0, None)
            predicted_100 = 100 * predicted_rate
            derivative = np.gradient(predicted_100, years) if len(years) > 1 else np.zeros_like(predicted_100)
            spline_frame = pd.DataFrame({
                "Species": species,
                "year": years,
                "predicted_abundance_per_sampling_event": predicted_rate,
                "predicted_abundance_per_100_sampling_events": predicted_100,
                "annual_derivative_per_100_sampling_events": derivative,
                "annual_derivative": derivative,
                "change_phase": np.select(
                    [derivative > 0.01, derivative < -0.01],
                    ["Aumento", "Descenso"],
                    default="Estable",
                ),
                "spline_offset_variable": "n_sampling_events",
            })
            prediction_frame = spline_frame.merge(prediction_frame, on=["Species", "year"], how="left") if prediction_frame is not None else spline_frame
        except Exception as exc:
            model_rows.append({
                **common,
                "model": "Spline-Poisson observation-rate",
                "status": f"failed: {type(exc).__name__}",
                "analysis_status": "not_estimable",
                "offset_variable": "n_sampling_events",
            })
        if prediction_frame is not None:
            predictions.append(prediction_frame)
    return pd.DataFrame(model_rows), pd.concat(predictions, ignore_index=True) if predictions else pd.DataFrame()

def _phase_segments(predictions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if predictions.empty or "change_phase" not in predictions:
        return pd.DataFrame(), pd.DataFrame()
    value_col = "predicted_abundance_per_100_sampling_events"
    derivative_col = "annual_derivative_per_100_sampling_events" if "annual_derivative_per_100_sampling_events" in predictions else "annual_derivative"
    segments: list[dict[str, Any]] = []
    change_points: list[dict[str, Any]] = []
    for species, frame in predictions.dropna(subset=["change_phase"]).groupby("Species", observed=True):
        frame = frame.sort_values("year").copy()
        frame["segment"] = frame["change_phase"].ne(frame["change_phase"].shift()).cumsum()
        for _, group in frame.groupby("segment"):
            segments.append({
                "Species": species,
                "phase": group["change_phase"].iloc[0],
                "start_year": int(group["year"].min()),
                "end_year": int(group["year"].max()),
                "duration_years": int(group["year"].max() - group["year"].min() + 1),
                "mean_derivative_per_100_sampling_events": group[derivative_col].mean(),
                "mean_derivative": group[derivative_col].mean(),
                "predicted_start_per_100_sampling_events": group[value_col].iloc[0],
                "predicted_end_per_100_sampling_events": group[value_col].iloc[-1],
                "predicted_start": group[value_col].iloc[0],
                "predicted_end": group[value_col].iloc[-1],
            })
        transitions = frame[frame["change_phase"].ne(frame["change_phase"].shift())].iloc[1:]
        for _, row in transitions.iterrows():
            change_points.append({
                "Species": species,
                "change_year": int(row["year"]),
                "new_phase": row["change_phase"],
                "derivative_at_change_per_100_sampling_events": row[derivative_col],
                "derivative_at_change": row[derivative_col],
            })
    return pd.DataFrame(segments), pd.DataFrame(change_points)

def _period_summary(table: pd.DataFrame, periods: list[Period], annual_period: pd.DataFrame | None = None) -> pd.DataFrame:
    """Returns raw metrics and metrics standardized by events, duration and space."""

    source = table.dropna(subset=["period"]).copy()
    source["Area_mar_km2"] = pd.to_numeric(source.get("Area_mar_km2"), errors="coerce")
    effort = source.groupby("period", observed=True).agg(
        n_records_period=("grid_id", "size"),
        n_sampling_events_period=("sampling_event_id", "nunique"),
        total_abundance_period=("N_aux", "sum"),
        n_years_period=("year", "nunique"),
        species_richness_period=("Species", "nunique"),
    ).reset_index()
    effort["n_months_period"] = effort["period"].map(
        source.assign(month=source["Fecha_aux"].dt.to_period("M")).groupby("period", observed=True)["month"].nunique()
    )
    sampled_space = (
        source[["period", "grid_id", "Area_mar_km2"]].drop_duplicates(["period", "grid_id"])
        .groupby("period", observed=True).agg(
            sampled_cells_period=("grid_id", "nunique"), sampled_area_period_km2=("Area_mar_km2", "sum")
        ).reset_index()
    )
    effort = effort.merge(sampled_space, on="period", how="left")
    definitions = _period_definition(table, periods)[[
        "period", "effective_duration_days", "effective_duration_years",
        "clipped_at_data_start", "clipped_at_data_end", "requested_interval_fully_covered",
    ]]
    effort = effort.merge(definitions, on="period", how="left")
    observed = source.groupby(["Species", "period"], observed=True).agg(
        n_records=("grid_id", "size"),
        species_sampling_events=("sampling_event_id", "nunique"),
        abundance=("N_aux", "sum"),
        detected_cells=("grid_id", "nunique"),
        depth_median=("Depth_aux", "median"),
        depth_mean=("Depth_aux", "mean"),
        habitat_dominant=("Habitat_aux", mode_or_na),
    ).reset_index()
    occupied_area = (
        source[["Species", "period", "grid_id", "Area_mar_km2"]].drop_duplicates(["Species", "period", "grid_id"])
        .groupby(["Species", "period"], observed=True)["Area_mar_km2"].sum()
        .rename("occupied_area_period_km2").reset_index()
    )
    observed = observed.merge(occupied_area, on=["Species", "period"], how="left")
    template = pd.MultiIndex.from_product(
        [sorted(table["Species"].dropna().unique()), [period.label for period in periods]],
        names=["Species", "period"],
    ).to_frame(index=False)
    result = template.merge(observed, on=["Species", "period"], how="left").merge(effort, on="period", how="left")
    for column in ("n_records", "species_sampling_events", "abundance", "detected_cells", "occupied_area_period_km2"):
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0)
    result["occupied_cells"] = result["detected_cells"]
    result["abundance_per_sampling_event_global_period"] = result["abundance"] / result["n_sampling_events_period"].replace(0, np.nan)
    result["abundance_per_record_global_period"] = result["abundance"] / result["n_records_period"].replace(0, np.nan)
    result["abundance_per_calendar_year_period"] = result["abundance"] / result["effective_duration_years"].replace(0, np.nan)
    result["abundance_per_sampled_year_period"] = result["abundance"] / result["n_years_period"].replace(0, np.nan)
    result["detection_frequency_sampled_cells_period"] = result["detected_cells"] / result["sampled_cells_period"].replace(0, np.nan)
    result["occupancy_prop_period"] = result["detection_frequency_sampled_cells_period"]
    result["abundance_per_sampled_cell_period"] = result["abundance"] / result["sampled_cells_period"].replace(0, np.nan)
    result["density_occupied_area_period_km2"] = np.where(
        result["occupied_area_period_km2"].gt(0),
        result["abundance"] / result["occupied_area_period_km2"],
        np.where(result["abundance"].eq(0), 0.0, np.nan),
    )
    annual_source = annual_period if annual_period is not None else _annual_period_metrics(table, periods)
    annual_means = annual_source.groupby(["Species", "period"], observed=True).agg(
        density_occupied_area_annualized_km2=("density_occupied_area_km2", "mean"),
        density_sampled_area_annualized_km2=("density_sampled_area_km2", "mean"),
    ).reset_index()
    result = result.merge(annual_means, on=["Species", "period"], how="left")
    result["density_annualization_basis"] = "mean_of_years_with_sampling"
    result["observation_rate_norm_period"] = result.groupby("Species", observed=True)["abundance_per_sampling_event_global_period"].transform(_rescale01)
    result["detection_frequency_norm_period"] = result.groupby("Species", observed=True)["detection_frequency_sampled_cells_period"].transform(_rescale01)
    result["period_relative_observation_index"] = 0.5 * (result["observation_rate_norm_period"] + result["detection_frequency_norm_period"])
    result["abundance_effort_norm_period"] = result["observation_rate_norm_period"]
    result["occupancy_norm_period"] = result["detection_frequency_norm_period"]
    result["period_population_index"] = result["period_relative_observation_index"]
    return result.sort_values(["Species", "period"]).reset_index(drop=True)

def _comparisons(table: pd.DataFrame, periods: list[Period], summaries: pd.DataFrame, annual_period: pd.DataFrame) -> pd.DataFrame:
    annual_test = annual_period.copy()
    rows: list[dict[str, Any]] = []
    for first, second in combinations(periods, 2):
        left = summaries[summaries["period"].eq(first.label)].set_index("Species")
        right = summaries[summaries["period"].eq(second.label)].set_index("Species")
        for species in sorted(set(left.index) | set(right.index)):
            a = left.loc[species] if species in left.index else pd.Series(dtype=float)
            b = right.loc[species] if species in right.index else pd.Series(dtype=float)
            first_records = table[(table["Species"].eq(species)) & (table["period"].eq(first.label))]["N_aux"]
            second_records = table[(table["Species"].eq(species)) & (table["period"].eq(second.label))]["N_aux"]
            if len(first_records) >= 2 and len(second_records) >= 2:
                record_level_test = stats.mannwhitneyu(first_records, second_records, alternative="two-sided")
                record_level_statistic, record_level_p_value = float(record_level_test.statistic), float(record_level_test.pvalue)
            else:
                record_level_statistic, record_level_p_value = np.nan, np.nan
            annual_species = annual_test[annual_test["Species"].eq(species)]
            annual_first = annual_species[annual_species["period"].eq(first.label)]
            annual_second = annual_species[annual_species["period"].eq(second.label)]
            kw_rate = _safe_kruskal(annual_first["abundance_per_sampling_event"], annual_second["abundance_per_sampling_event"])
            kw_detection = _safe_kruskal(annual_first["detection_frequency_sampled_cells"], annual_second["detection_frequency_sampled_cells"])
            kw_index = _safe_kruskal(annual_first["annual_relative_observation_index"], annual_second["annual_relative_observation_index"])
            abundance_1, abundance_2 = float(a.get("abundance", 0)), float(b.get("abundance", 0))
            cells_1, cells_2 = float(a.get("detected_cells", a.get("occupied_cells", 0))), float(b.get("detected_cells", b.get("occupied_cells", 0)))
            rate_1 = a.get("abundance_per_sampling_event_global_period", np.nan)
            rate_2 = b.get("abundance_per_sampling_event_global_period", np.nan)
            rows.append({
                "comparison": f"{first.label} vs {second.label}", "period_1": first.label, "period_2": second.label, "Species": species,
                "abundance_1": abundance_1, "abundance_2": abundance_2, "delta_abundance": abundance_2 - abundance_1,
                "relative_change_abundance_raw_pct": 100 * (abundance_2 - abundance_1) / abundance_1 if abundance_1 > 0 else np.nan,
                "abundance_per_sampling_event_1": rate_1, "abundance_per_sampling_event_2": rate_2,
                "delta_abundance_event_rate": rate_2 - rate_1,
                "relative_change_abundance_pct": 100 * (rate_2 - rate_1) / rate_1 if pd.notna(rate_1) and rate_1 > 0 else np.nan,
                "abundance_per_record_1": a.get("abundance_per_record_global_period", np.nan),
                "abundance_per_record_2": b.get("abundance_per_record_global_period", np.nan),
                "delta_abundance_effort": rate_2 - rate_1,
                "occupied_cells_1": cells_1, "occupied_cells_2": cells_2, "delta_occupied_cells": cells_2 - cells_1,
                "sampled_cells_1": a.get("sampled_cells_period", np.nan), "sampled_cells_2": b.get("sampled_cells_period", np.nan),
                "detection_frequency_1": a.get("detection_frequency_sampled_cells_period", np.nan),
                "detection_frequency_2": b.get("detection_frequency_sampled_cells_period", np.nan),
                "delta_detection_frequency": b.get("detection_frequency_sampled_cells_period", np.nan) - a.get("detection_frequency_sampled_cells_period", np.nan),
                "occupancy_prop_1": a.get("detection_frequency_sampled_cells_period", np.nan),
                "occupancy_prop_2": b.get("detection_frequency_sampled_cells_period", np.nan),
                "delta_occupancy": b.get("detection_frequency_sampled_cells_period", np.nan) - a.get("detection_frequency_sampled_cells_period", np.nan),
                "pct_change_occupancy": 100 * (b.get("detection_frequency_sampled_cells_period", np.nan) - a.get("detection_frequency_sampled_cells_period", np.nan)) / a.get("detection_frequency_sampled_cells_period", np.nan) if a.get("detection_frequency_sampled_cells_period", 0) > 0 else np.nan,
                "relative_observation_index_1": a.get("period_relative_observation_index", np.nan),
                "relative_observation_index_2": b.get("period_relative_observation_index", np.nan),
                "delta_relative_observation_index": b.get("period_relative_observation_index", np.nan) - a.get("period_relative_observation_index", np.nan),
                "population_index_1": a.get("period_relative_observation_index", np.nan),
                "population_index_2": b.get("period_relative_observation_index", np.nan),
                "delta_population_index": b.get("period_relative_observation_index", np.nan) - a.get("period_relative_observation_index", np.nan),
                "annualized_density_1": a.get("density_occupied_area_annualized_km2", np.nan), "annualized_density_2": b.get("density_occupied_area_annualized_km2", np.nan),
                "delta_annualized_density": b.get("density_occupied_area_annualized_km2", np.nan) - a.get("density_occupied_area_annualized_km2", np.nan),
                "duration_years_1": a.get("effective_duration_years", np.nan), "duration_years_2": b.get("effective_duration_years", np.nan),
                "sampled_years_1": a.get("n_years_period", np.nan), "sampled_years_2": b.get("n_years_period", np.nan),
                "sampling_events_1": a.get("n_sampling_events_period", np.nan), "sampling_events_2": b.get("n_sampling_events_period", np.nan),
                "effort_records_1": a.get("n_records_period", np.nan), "effort_records_2": b.get("n_records_period", np.nan),
                "period_1_clipped_at_data_end": bool(a.get("clipped_at_data_end", False)), "period_2_clipped_at_data_end": bool(b.get("clipped_at_data_end", False)),
                "depth_median_1": a.get("depth_median", np.nan), "depth_median_2": b.get("depth_median", np.nan), "delta_depth_median": b.get("depth_median", np.nan) - a.get("depth_median", np.nan),
                "mann_whitney_U": record_level_statistic, "mann_whitney_p_value_records": record_level_p_value,
                "kw_stat_abundance_effort": kw_rate[0], "kw_p_abundance_effort": kw_rate[1],
                "kw_stat_detection_frequency": kw_detection[0], "kw_p_detection_frequency": kw_detection[1],
                "kw_stat_occupancy": kw_detection[0], "kw_p_occupancy": kw_detection[1],
                "kw_stat_relative_observation_index": kw_index[0], "kw_p_relative_observation_index": kw_index[1],
                "kw_stat_population_index": kw_index[0], "kw_p_population_index": kw_index[1],
                "statistical_unit": "year", "primary_change_metric": "abundance_per_sampling_event_global_period",
            })
    result = pd.DataFrame(rows)
    if not result.empty:
        result["p_value"] = result["kw_p_abundance_effort"]
        result["p_adjust_BH"] = _adjust_valid_pvalues(result["p_value"])
        for column in ("kw_p_abundance_effort", "kw_p_detection_frequency", "kw_p_relative_observation_index", "kw_p_occupancy", "kw_p_population_index"):
            result[f"{column}_adjust_BH"] = _adjust_valid_pvalues(result[column])
    return result

def _cell_changes(table: pd.DataFrame, periods: list[Period], occupied_cells: gpd.GeoDataFrame) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Compares species across the union of sampled official marine cells."""

    source = table.dropna(subset=["period"]).copy()
    source["grid_id"] = source["grid_id"].astype(str)
    source["Area_mar_km2"] = pd.to_numeric(source.get("Area_mar_km2"), errors="coerce")
    summary = source.groupby(["grid_id", "Species", "period"], observed=True).agg(
        abundance=("N_aux", "sum"), n_records=("grid_id", "size"), species_sampling_events=("sampling_event_id", "nunique"),
        depth_median=("Depth_aux", "median"), habitat_dominant=("Habitat_aux", mode_or_na),
    ).reset_index()
    sampling = source.groupby(["grid_id", "period"], observed=True).agg(
        effort_records_cell_period=("grid_id", "size"), n_sampling_events_cell_period=("sampling_event_id", "nunique"), sampled_years_cell_period=("year", "nunique"),
    ).reset_index()
    attributes = source.groupby("grid_id", observed=True).agg(Area_mar_km2=("Area_mar_km2", "first"), Region_MITECO=("Region_MITECO", mode_or_na)).reset_index()
    species_values = sorted(source["Species"].dropna().unique())
    rows: list[pd.DataFrame] = []
    for first, second in combinations(periods, 2):
        sampled_first = sampling[sampling["period"].eq(first.label)][["grid_id", "effort_records_cell_period", "n_sampling_events_cell_period", "sampled_years_cell_period"]].rename(columns={
            "effort_records_cell_period": "effort_records_cell_1", "n_sampling_events_cell_period": "sampling_events_cell_1", "sampled_years_cell_period": "sampled_years_cell_1"})
        sampled_second = sampling[sampling["period"].eq(second.label)][["grid_id", "effort_records_cell_period", "n_sampling_events_cell_period", "sampled_years_cell_period"]].rename(columns={
            "effort_records_cell_period": "effort_records_cell_2", "n_sampling_events_cell_period": "sampling_events_cell_2", "sampled_years_cell_period": "sampled_years_cell_2"})
        sampled = sampled_first.merge(sampled_second, on="grid_id", how="outer")
        sampled["sampled_1"] = sampled["sampling_events_cell_1"].notna()
        sampled["sampled_2"] = sampled["sampling_events_cell_2"].notna()
        sampled["sampled_union"] = sampled["sampled_1"] | sampled["sampled_2"]
        sampled["sampled_intersection"] = sampled["sampled_1"] & sampled["sampled_2"]
        base = pd.MultiIndex.from_product([species_values, sorted(sampled.loc[sampled["sampled_union"], "grid_id"])], names=["Species", "grid_id"]).to_frame(index=False)
        base = base.merge(sampled, on="grid_id", how="left").merge(attributes, on="grid_id", how="left")
        left = summary[summary["period"].eq(first.label)].drop(columns="period").rename(columns={
            "abundance": "abundance_1", "n_records": "n_records_species_cell_1", "species_sampling_events": "species_sampling_events_cell_1", "depth_median": "depth_median_1", "habitat_dominant": "habitat_dominant_1"})
        right = summary[summary["period"].eq(second.label)].drop(columns="period").rename(columns={
            "abundance": "abundance_2", "n_records": "n_records_species_cell_2", "species_sampling_events": "species_sampling_events_cell_2", "depth_median": "depth_median_2", "habitat_dominant": "habitat_dominant_2"})
        wide = base.merge(left, on=["grid_id", "Species"], how="left").merge(right, on=["grid_id", "Species"], how="left")
        for column in ("abundance_1", "abundance_2", "n_records_species_cell_1", "n_records_species_cell_2", "species_sampling_events_cell_1", "species_sampling_events_cell_2"):
            wide[column] = pd.to_numeric(wide[column], errors="coerce").fillna(0)
        wide["presence_1"] = wide["abundance_1"].gt(0); wide["presence_2"] = wide["abundance_2"].gt(0)
        wide["period_1"], wide["period_2"] = first.label, second.label
        wide["comparison"] = f"{first.label} vs {second.label}"
        wide["duration_years_1"], wide["duration_years_2"] = _duration_years(first), _duration_years(second)
        wide["delta_abundance"] = wide["abundance_2"] - wide["abundance_1"]
        valid_area = pd.to_numeric(wide["Area_mar_km2"], errors="coerce").gt(0)
        wide["density_1"] = np.where(valid_area, wide["abundance_1"] / wide["Area_mar_km2"], np.nan)
        wide["density_2"] = np.where(valid_area, wide["abundance_2"] / wide["Area_mar_km2"], np.nan)
        wide["annualized_density_1"] = wide["density_1"] / wide["sampled_years_cell_1"].replace(0, np.nan)
        wide["annualized_density_2"] = wide["density_2"] / wide["sampled_years_cell_2"].replace(0, np.nan)
        wide["delta_density"] = wide["density_2"] - wide["density_1"]
        wide["delta_annualized_density"] = wide["annualized_density_2"] - wide["annualized_density_1"]
        wide["abundance_per_sampling_event_cell_1"] = np.where(wide["sampling_events_cell_1"].fillna(0).gt(0), wide["abundance_1"] / wide["sampling_events_cell_1"], np.nan)
        wide["abundance_per_sampling_event_cell_2"] = np.where(wide["sampling_events_cell_2"].fillna(0).gt(0), wide["abundance_2"] / wide["sampling_events_cell_2"], np.nan)
        wide["delta_abundance_per_sampling_event_cell"] = wide["abundance_per_sampling_event_cell_2"] - wide["abundance_per_sampling_event_cell_1"]
        wide["abundance_per_record_cell_1"] = np.where(wide["effort_records_cell_1"].fillna(0).gt(0), wide["abundance_1"] / wide["effort_records_cell_1"], np.nan)
        wide["abundance_per_record_cell_2"] = np.where(wide["effort_records_cell_2"].fillna(0).gt(0), wide["abundance_2"] / wide["effort_records_cell_2"], np.nan)
        wide["delta_abundance_per_record_cell"] = wide["abundance_per_record_cell_2"] - wide["abundance_per_record_cell_1"]
        wide["status_union_assumption"] = np.select([~wide["presence_1"] & wide["presence_2"], wide["presence_1"] & ~wide["presence_2"], wide["presence_1"] & wide["presence_2"]], ["Ganancia", "Pérdida", "Persistencia"], default="Ausencia en ambos")
        wide["comparison_valid"] = wide["sampled_intersection"]
        wide["status"] = np.select([~wide["comparison_valid"], ~wide["presence_1"] & wide["presence_2"], wide["presence_1"] & ~wide["presence_2"], wide["presence_1"] & wide["presence_2"]], ["No comparable", "Ganancia", "Pérdida", "Persistencia"], default="Ausencia en ambos")
        wide["non_comparable_reason"] = np.select([wide["sampled_1"] & ~wide["sampled_2"], ~wide["sampled_1"] & wide["sampled_2"]], ["No sampling in period 2", "No sampling in period 1"], default="")
        rows.append(wide)
    changes = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["comparison"])
    geometry = occupied_cells[["grid_id", "geometry"]].drop_duplicates("grid_id").copy(); geometry["grid_id"] = geometry["grid_id"].astype(str)
    spatial = geometry.merge(changes, on="grid_id", how="inner") if not changes.empty else geometry.iloc[0:0]
    return changes, gpd.GeoDataFrame(spatial, geometry="geometry", crs=occupied_cells.crs)

def _temporal_signal_for_key(table: pd.DataFrame, periods: list[Period], key: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calcula magnitud temporal 0-1 para una clave espacial explícita."""

    source = table.dropna(subset=["period", key]).copy()
    if source.empty or len(periods) < 2:
        return pd.DataFrame(columns=[key, "temporal_signal_raw", "n_temporal_records", "n_temporal_sampling_events"]), pd.DataFrame()
    source[key] = source[key].astype(str)
    source["Area_mar_km2"] = pd.to_numeric(source.get("Area_mar_km2"), errors="coerce")
    effort_year = source.groupby([key, "period", "year"], observed=True).agg(
        effort_records_year=(key, "size"), n_sampling_events_year=("sampling_event_id", "nunique")
    ).reset_index()
    area_columns = [key, "period", "year", "Area_mar_km2"]
    area_dedup = [key, "period", "year"]
    if key != "grid_id":
        area_columns.insert(3, "grid_id")
        area_dedup.append("grid_id")
    sampled_area_year = (
        source[area_columns]
        .drop_duplicates(area_dedup)
        .groupby([key, "period", "year"], observed=True)["Area_mar_km2"].sum()
        .rename("sampled_marine_area_year_km2").reset_index()
    )
    effort_year = effort_year.merge(sampled_area_year, on=[key, "period", "year"], how="left")
    observed_year = source.groupby([key, "Species", "period", "year"], observed=True)["N_aux"].sum().rename("abundance_year").reset_index()
    species = pd.DataFrame({"Species": sorted(source["Species"].dropna().unique())})
    species["_cross"], effort_year["_cross"] = 1, 1
    complete_year = species.merge(effort_year, on="_cross").drop(columns="_cross")
    complete_year = complete_year.merge(observed_year, on=[key, "Species", "period", "year"], how="left")
    complete_year["abundance_year"] = complete_year["abundance_year"].fillna(0)
    complete_year["observation_rate_year"] = complete_year["abundance_year"] / complete_year["n_sampling_events_year"].replace(0, np.nan)
    complete_year["detection_year"] = complete_year["abundance_year"].gt(0).astype(float)
    complete_year["marine_density_year_km2"] = complete_year["abundance_year"] / complete_year["sampled_marine_area_year_km2"].replace(0, np.nan)
    period_species = complete_year.groupby([key, "Species", "period"], observed=True).agg(
        abundance=("abundance_year", "sum"), observation_rate=("observation_rate_year", "mean"),
        detection_frequency=("detection_year", "mean"), annualized_density=("marine_density_year_km2", "mean"),
        sampled_years=("year", "nunique"), n_sampling_events=("n_sampling_events_year", "sum"), effort_records=("effort_records_year", "sum"),
    ).reset_index()
    components: list[pd.DataFrame] = []
    for first, second in combinations(periods, 2):
        left = period_species[period_species["period"].eq(first.label)].drop(columns="period").rename(columns={
            "abundance": "abundance_1", "observation_rate": "observation_rate_1", "detection_frequency": "detection_frequency_1", "annualized_density": "annualized_density_1", "sampled_years": "sampled_years_1", "n_sampling_events": "sampling_events_1", "effort_records": "effort_records_1"})
        right = period_species[period_species["period"].eq(second.label)].drop(columns="period").rename(columns={
            "abundance": "abundance_2", "observation_rate": "observation_rate_2", "detection_frequency": "detection_frequency_2", "annualized_density": "annualized_density_2", "sampled_years": "sampled_years_2", "n_sampling_events": "sampling_events_2", "effort_records": "effort_records_2"})
        wide = left.merge(right, on=[key, "Species"], how="inner")
        if wide.empty:
            continue
        wide["sampled_1"] = True; wide["sampled_2"] = True; wide["sampled_intersection"] = True
        wide["comparison"] = f"{first.label} vs {second.label}"
        wide["observation_rate_component"], wide["observation_rate_change_signed"] = _symmetric_relative_change(wide["observation_rate_1"], wide["observation_rate_2"])
        wide["detection_frequency_component"] = (wide["detection_frequency_2"] - wide["detection_frequency_1"]).abs()
        wide["detection_frequency_change_signed"] = wide["detection_frequency_2"] - wide["detection_frequency_1"]
        wide["marine_density_component"], wide["marine_density_change_signed"] = _symmetric_relative_change(wide["annualized_density_1"], wide["annualized_density_2"])
        wide["abundance_effort_component"] = wide["observation_rate_component"]
        wide["occupancy_component"] = wide["detection_frequency_component"]
        wide["change_signal"] = wide[["observation_rate_component", "detection_frequency_component", "marine_density_component"]].mean(axis=1, skipna=False)
        wide["signal_formula"] = "equal_weights_symmetric_observation_rate_detection_frequency_marine_density_v3"
        components.append(wide)
    if not components:
        return pd.DataFrame(columns=[key, "temporal_signal_raw", "n_temporal_records", "n_temporal_sampling_events"]), pd.DataFrame()
    detail = pd.concat(components, ignore_index=True)
    support = source.groupby(key, observed=True).agg(n_temporal_records=(key, "size"), n_temporal_sampling_events=("sampling_event_id", "nunique"))
    summary = detail.groupby(key, observed=True).agg(
        temporal_signal_raw=("change_signal", "mean"), observation_rate_component=("observation_rate_component", "mean"),
        detection_frequency_component=("detection_frequency_component", "mean"), marine_density_component=("marine_density_component", "mean"),
        n_temporal_comparisons=("comparison", "nunique"), n_temporal_component_rows=("change_signal", "size"),
    ).join(support).reset_index()
    summary["abundance_effort_component"] = summary["observation_rate_component"]
    summary["occupancy_component"] = summary["detection_frequency_component"]
    summary["signal_formula"] = "equal_weights_symmetric_observation_rate_detection_frequency_marine_density_v3"
    return summary, detail


def _fine_temporal_signal(table: pd.DataFrame, periods: list[Period], selected_grid_km: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Auxiliary temporal signal on an internal regular key for technical checks.

    The analytical signal used by conservation is calculated on the official
    MITECO grid by ``_official_temporal_signal``.
    """

    size = selected_grid_km * 1000.0
    ix = np.floor(table["coord_x"] / size).astype(int)
    iy = np.floor(table["coord_y"] / size).astype(int)
    prefix = f"s{selected_grid_km}_"
    fine = table.assign(master_id=prefix + ix.astype(str) + "_" + iy.astype(str))
    return _temporal_signal_for_key(fine, periods, "master_id")


def _official_temporal_signal(table: pd.DataFrame, periods: list[Period]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Canonical temporal signal on the selected official MITECO cell."""

    summary, detail = _temporal_signal_for_key(table, periods, "grid_id")
    if not summary.empty:
        summary["spatial_key"] = "official_miteco_grid_id"
    if not detail.empty:
        detail["spatial_key"] = "official_miteco_grid_id"
    return summary, detail

def _temporal_quality_control(
    table: pd.DataFrame,
    periods: list[Period],
    annual_period: pd.DataFrame,
    period_summary: pd.DataFrame,
    comparisons: pd.DataFrame,
    changes: pd.DataFrame,
    temporal_signal: pd.DataFrame,
    temporal_signal_detail: pd.DataFrame,
) -> pd.DataFrame:
    """Fail-fast mathematical controls for the temporal analysis basis."""

    checks: list[dict[str, Any]] = []

    def add(name: str, condition: bool, detail: Any) -> None:
        checks.append(
            {"check": name, "status": "PASS" if bool(condition) else "FAIL", "detail": detail}
        )

    area = pd.to_numeric(table["Area_mar_km2"], errors="coerce")
    add("positive_official_marine_area", bool(area.notna().all() and area.gt(0).all()), int(area.notna().sum()))
    add(
        "official_marine_area_unique_per_cell",
        bool(table.groupby("grid_id", observed=True)["Area_mar_km2"].nunique().le(1).all()),
        int(table["grid_id"].nunique()),
    )
    raw_expected = table.dropna(subset=["period"]).groupby("period", observed=True)["N_aux"].sum()
    raw_actual = period_summary.groupby("period", observed=True)["abundance"].sum()
    raw_difference = raw_expected.subtract(raw_actual, fill_value=0).abs()
    add("period_raw_abundance_conserved", bool(np.allclose(raw_difference, 0, atol=1e-10)), float(raw_difference.max()) if len(raw_difference) else 0.0)

    expected_rate = period_summary["abundance"] / period_summary["n_sampling_events_period"].replace(0, np.nan)
    add(
        "period_event_rate_reproducible",
        bool(np.allclose(expected_rate, period_summary["abundance_per_sampling_event_global_period"], equal_nan=True, rtol=1e-12, atol=1e-12)),
        int(len(period_summary)),
    )
    add(
        "sampling_events_do_not_exceed_records",
        bool((period_summary["n_sampling_events_period"] <= period_summary["n_records_period"]).all()),
        int(len(period_summary)),
    )
    expected_detection = period_summary["detected_cells"] / period_summary["sampled_cells_period"].replace(0, np.nan)
    add(
        "period_detection_frequency_reproducible",
        bool(np.allclose(expected_detection, period_summary["detection_frequency_sampled_cells_period"], equal_nan=True, rtol=1e-12, atol=1e-12)),
        int(len(period_summary)),
    )
    add(
        "period_detection_frequency_bounded",
        bool(period_summary["detection_frequency_sampled_cells_period"].dropna().between(0, 1).all()),
        int(period_summary["detection_frequency_sampled_cells_period"].notna().sum()),
    )
    expected_density = (
        annual_period.groupby(["Species", "period"], observed=True)[
            "density_occupied_area_km2"
        ]
        .mean()
        .rename("expected_density")
        .reset_index()
    )
    density_check = period_summary[[
        "Species", "period", "density_occupied_area_annualized_km2"
    ]].merge(expected_density, on=["Species", "period"], how="left")
    add(
        "annualized_marine_density_reproducible",
        bool(np.allclose(
            density_check["expected_density"],
            density_check["density_occupied_area_annualized_km2"],
            equal_nan=True,
            rtol=1e-12,
            atol=1e-10,
        )),
        int(len(period_summary)),
    )
    add(
        "positive_sampled_years_per_period",
        bool(period_summary["n_years_period"].gt(0).all()),
        period_summary.groupby("period", observed=True)["n_years_period"].first().to_dict(),
    )
    expected_rows = 0
    universe_ok = True
    for _, frame in changes.groupby("comparison", observed=True):
        expected = frame["Species"].nunique() * frame["grid_id"].nunique()
        expected_rows += int(expected)
        universe_ok &= len(frame) == expected and not frame.duplicated(["Species", "grid_id"]).any()
    add("sampled_cell_union_complete", bool(universe_ok), {"expected": expected_rows, "actual": int(len(changes))})
    if changes.empty:
        status_ok = True
    else:
        expected_status = np.select(
            [
                ~changes["sampled_intersection"],
                ~changes["presence_1"] & changes["presence_2"],
                changes["presence_1"] & ~changes["presence_2"],
                changes["presence_1"] & changes["presence_2"],
            ],
            ["No comparable", "Ganancia", "Pérdida", "Persistencia"],
            default="Ausencia en ambos",
        )
        status_ok = bool(np.array_equal(changes["status"].astype(str).to_numpy(), expected_status))
    add("cell_change_status_reproducible", status_ok, int(len(changes)))
    add(
        "unsampled_cells_not_interpreted_as_change",
        bool(
            changes.empty
            or changes.loc[~changes["sampled_intersection"], "status"].eq(
                "No comparable"
            ).all()
        ),
        int((~changes["sampled_intersection"]).sum()) if not changes.empty else 0,
    )
    add(
        "non_calculable_pvalues_preserved",
        bool(
            comparisons.empty
            or comparisons.loc[comparisons["p_value"].isna(), "p_adjust_BH"].isna().all()
        ),
        int(comparisons["p_value"].isna().sum()) if not comparisons.empty else 0,
    )
    add(
        "temporal_signal_bounded",
        bool(temporal_signal.empty or temporal_signal["temporal_signal_raw"].dropna().between(0, 1).all()),
        int(len(temporal_signal)),
    )
    add(
        "temporal_signal_explicit_formula",
        bool(
            temporal_signal.empty
            or temporal_signal["signal_formula"].eq(
                "equal_weights_symmetric_observation_rate_detection_frequency_marine_density_v3"
            ).all()
        ),
        "equal weights: event-based relative observation rate, temporal detection frequency and marine density; symmetric unit-invariant changes",
    )
    add(
        "temporal_signal_uses_sampled_intersection",
        bool(
            temporal_signal_detail.empty
            or temporal_signal_detail["sampled_intersection"].fillna(False).all()
        ),
        int(len(temporal_signal_detail)),
    )
    add("positive_effective_period_duration", bool(all(_duration_years(period) > 0 for period in periods)), len(periods))
    valid_depth = table["Depth_aux"].dropna()
    add("temporal_depth_within_0_200m", bool(valid_depth.between(0, 200).all()), int(len(valid_depth)))
    frame = pd.DataFrame(checks)
    failed = frame.loc[frame["status"].eq("FAIL"), "check"].tolist()
    if failed:
        raise AssertionError("Temporal analysis checks failed: " + ", ".join(failed))
    return frame


def _ranking(annual: pd.DataFrame, comparisons: pd.DataFrame, models: pd.DataFrame) -> pd.DataFrame:
    base = annual.groupby("Species", observed=True).agg(
        observation_rate_mean=("abundance_per_100_sampling_events", "mean"),
        observation_rate_cv=("abundance_per_100_sampling_events", lambda x: x.std() / x.mean() if x.mean() > 0 else np.nan),
        detection_frequency_mean=("detection_frequency_sampled_cells_pct", "mean"),
        detection_frequency_cv=("detection_frequency_sampled_cells_pct", lambda x: x.std() / x.mean() if x.mean() > 0 else np.nan),
        active_years=("abundance", lambda x: int((x > 0).sum())),
    ).reset_index()
    # Internal convenience fields; public outputs use observation-rate and detection-frequency terminology.
    base["abundance_mean"] = base["observation_rate_mean"]
    base["abundance_cv"] = base["observation_rate_cv"]
    base["occupancy_mean"] = base["detection_frequency_mean"]
    base["occupancy_cv"] = base["detection_frequency_cv"]
    changes = comparisons.groupby("Species").agg(
        max_abs_abundance_change=("relative_change_abundance_pct", lambda x: np.nanmax(np.abs(x)) if x.notna().any() else np.nan),
        max_abs_cell_change=("delta_occupied_cells", lambda x: np.nanmax(np.abs(x)) if x.notna().any() else np.nan),
        max_abs_detection_frequency_change=("delta_detection_frequency", lambda x: np.nanmax(np.abs(x)) if x.notna().any() else np.nan),
    ).reset_index() if not comparisons.empty else pd.DataFrame({"Species": pd.Series(dtype="string"), "max_abs_abundance_change": pd.Series(dtype=float), "max_abs_cell_change": pd.Series(dtype=float), "max_abs_detection_frequency_change": pd.Series(dtype=float)})
    if not changes.empty:
        changes["max_abs_occupancy_change"] = changes["max_abs_detection_frequency_change"]
    primary = models[(models["model"].astype(str).eq("Poisson-Pearson observation-rate trend")) & (models["status"].eq("ok"))][["Species", "annual_change_pct", "p_value", "pearson_dispersion_used"]] if not models.empty and "annual_change_pct" in models else pd.DataFrame({"Species": pd.Series(dtype="string"), "annual_change_pct": pd.Series(dtype=float), "p_value": pd.Series(dtype=float), "pearson_dispersion_used": pd.Series(dtype=float)})
    support = models[models["model"].astype(str).eq("Poisson-Pearson observation-rate trend")][[c for c in ("Species", "inference_scope", "n_detection_years", "n_detection_events", "detection_span_years", "support_reason") if c in models.columns]].drop_duplicates("Species") if not models.empty else pd.DataFrame()
    result = base.merge(changes, on="Species", how="left").merge(primary, on="Species", how="left")
    if not support.empty:
        for col in support.columns:
            if col != "Species" and col in result.columns:
                support = support.drop(columns=col)
        result = result.merge(support, on="Species", how="left")
    result["complexity_score"] = 35 * _rescale01(result["observation_rate_cv"].fillna(0)) + 35 * _rescale01(result["detection_frequency_cv"].fillna(0)) + 30 * _rescale01(result["max_abs_abundance_change"].fillna(0))
    result["stability_score"] = 100 - result["complexity_score"]
    result["change_score"] = 50 * _rescale01(result["max_abs_abundance_change"].fillna(0)) + 30 * _rescale01(result["max_abs_detection_frequency_change"].fillna(0)) + 20 * _rescale01(result["annual_change_pct"].abs().fillna(0))
    result["temporal_priority_score"] = 0.6 * result["change_score"] + 0.4 * result["complexity_score"]
    result["temporal_priority_rank"] = result["temporal_priority_score"].rank(method="dense", ascending=False).astype("Int64")
    result["trend_direction"] = np.select([result["annual_change_pct"] > 0, result["annual_change_pct"] < 0], ["Aumento", "Descenso"], default="Sin tendencia inferencial estimable")
    result["ranking_method"] = "observation_event_proxy_and_detection_frequency_v3"
    return result.sort_values("temporal_priority_rank")

def _temporal_support_tables(
    table: pd.DataFrame,
    annual: pd.DataFrame,
    periods: list[Period],
    changes: pd.DataFrame,
    comparisons: pd.DataFrame,
    predictions: pd.DataFrame,
    phases: pd.DataFrame,
    change_points: pd.DataFrame,
    ranking: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Build the explicit auxiliary tables for block 20 of the R script."""
    usable_depth = table.dropna(subset=["Depth_aux"])
    habitat_trace = (
        table.assign(
            habitat_informative=table["Habitat_aux"].notna()
            & table["Habitat_aux"].ne("")
        )
        .groupby("year", observed=True)
        .agg(
            records_total=("grid_id", "size"),
            records_with_habitat=("habitat_informative", "sum"),
            habitats_distinct=("Habitat_aux", "nunique"),
        )
        .reset_index()
    )
    habitat_trace["habitat_coverage_pct"] = (
        100
        * habitat_trace["records_with_habitat"]
        / habitat_trace["records_total"].replace(0, np.nan)
    )
    control = pd.DataFrame(
        {
            "variable": ["Habitat", "Depth"],
            "records_total": [len(table), len(table)],
            "records_informative": [
                int(table["Habitat_aux"].notna().sum()),
                int(table["Depth_aux"].notna().sum()),
            ],
        }
    )
    control["coverage_pct"] = (
        100 * control["records_informative"] / control["records_total"].replace(0, np.nan)
    )
    annual_global = (
        table.groupby("year", observed=True)
        .agg(
            n_records=("grid_id", "size"),
            n_sampling_events=("sampling_event_id", "nunique"),
            abundance=("N_aux", "sum"),
            depth_mean=("Depth_aux", "mean"),
            depth_median=("Depth_aux", "median"),
            depth_sd=("Depth_aux", "std"),
            habitat_dominant=("Habitat_aux", mode_or_na),
            habitat_richness=("Habitat_aux", "nunique"),
        )
        .reset_index()
    )
    annual_species = (
        table.groupby(["Species", "year"], observed=True)
        .agg(
            n_records=("grid_id", "size"),
            n_sampling_events=("sampling_event_id", "nunique"),
            abundance=("N_aux", "sum"),
            occupied_cells=("grid_id", "nunique"),
            depth_mean=("Depth_aux", "mean"),
            depth_median=("Depth_aux", "median"),
            habitat_dominant=("Habitat_aux", mode_or_na),
            habitat_richness=("Habitat_aux", "nunique"),
        )
        .reset_index()
    )

    depth_trends: list[dict[str, Any]] = []
    for species, frame in annual_species.groupby("Species", observed=True):
        fit = frame.dropna(subset=["depth_median"])
        if len(fit) >= 3 and fit["year"].nunique() >= 3:
            slope, intercept, r, p, se = stats.linregress(fit["year"], fit["depth_median"])
        else:
            slope = intercept = r = p = se = np.nan
        depth_trends.append(
            {
                "Species": species,
                "n_years": int(fit["year"].nunique()),
                "depth_slope_m_per_year": slope,
                "intercept": intercept,
                "r_squared": r**2 if pd.notna(r) else np.nan,
                "p_value": p,
                "standard_error": se,
            }
        )
    depth_trends_frame = pd.DataFrame(depth_trends)

    habitat_period = (
        table.dropna(subset=["period"])
        .groupby(["Species", "period"], observed=True)
        .agg(
            n_records=("grid_id", "size"),
            depth_mean=("Depth_aux", "mean"),
            depth_median=("Depth_aux", "median"),
            habitat_dominant=("Habitat_aux", mode_or_na),
            habitat_richness=("Habitat_aux", "nunique"),
        )
        .reset_index()
    )
    habitat_cell_period = (
        table.dropna(subset=["period"])
        .groupby(["grid_id", "Species", "period"], observed=True)
        .agg(
            n_records=("grid_id", "size"),
            n_sampling_events=("sampling_event_id", "nunique"),
            abundance=("N_aux", "sum"),
            depth_mean=("Depth_aux", "mean"),
            depth_median=("Depth_aux", "median"),
            habitat_dominant=("Habitat_aux", mode_or_na),
        )
        .reset_index()
    )
    cell_period = (
        table.dropna(subset=["period"])
        .groupby(["grid_id", "Species", "period"], observed=True)
        .agg(abundance=("N_aux", "sum"), n_records=("grid_id", "size"))
        .reset_index()
    )

    balance = (
        changes.groupby(["Species", "comparison"], observed=True)
        .agg(
            gains=("status", lambda x: int(x.eq("Ganancia").sum())),
            losses=("status", lambda x: int(x.eq("Pérdida").sum())),
            persistence=("status", lambda x: int(x.eq("Persistencia").sum())),
            absence_both=("status", lambda x: int(x.eq("Ausencia en ambos").sum())),
            non_comparable=("status", lambda x: int(x.eq("No comparable").sum())),
            delta_abundance=("delta_abundance", "sum"),
            delta_annualized_density=("delta_annualized_density", "sum"),
            cells_evaluated=("grid_id", "nunique"),
            sampled_intersection_grids=("sampled_intersection", "sum"),
        )
        .reset_index()
        if not changes.empty
        else pd.DataFrame()
    )
    if not balance.empty:
        balance["turnover_cells"] = balance["gains"] + balance["losses"]
        balance["net_spatial_balance"] = balance["gains"] - balance["losses"]
        balance["persistence_pct"] = 100 * balance["persistence"] / (
            balance["persistence"] + balance["gains"] + balance["losses"]
        ).replace(0, np.nan)
    spatial_indices = balance.copy()
    if not spatial_indices.empty:
        presence_union = (
            spatial_indices["persistence"]
            + spatial_indices["gains"]
            + spatial_indices["losses"]
        )
        spatial_indices["sampled_union_grids"] = spatial_indices["cells_evaluated"]
        spatial_indices["comparable_sampled_grids"] = spatial_indices[
            "sampled_intersection_grids"
        ]
        spatial_indices["jaccard_similarity"] = (
            spatial_indices["persistence"] / presence_union.replace(0, np.nan)
        )
        spatial_indices["turnover_rate"] = (
            (spatial_indices["gains"] + spatial_indices["losses"])
            / presence_union.replace(0, np.nan)
        )
        spatial_indices["persist_prop_union"] = spatial_indices["persistence"] / spatial_indices["sampled_union_grids"].replace(0, np.nan)
        spatial_indices["gain_prop_union"] = spatial_indices["gains"] / spatial_indices["sampled_union_grids"].replace(0, np.nan)
        spatial_indices["loss_prop_union"] = spatial_indices["losses"] / spatial_indices["sampled_union_grids"].replace(0, np.nan)
        spatial_indices["net_change_prop_union"] = (
            spatial_indices["gains"] - spatial_indices["losses"]
        ) / spatial_indices["sampled_union_grids"].replace(0, np.nan)
        spatial_indices["persist_prop_comparable"] = spatial_indices["persistence"] / spatial_indices["comparable_sampled_grids"].replace(0, np.nan)
        spatial_indices["gain_prop_comparable"] = spatial_indices["gains"] / spatial_indices["comparable_sampled_grids"].replace(0, np.nan)
        spatial_indices["loss_prop_comparable"] = spatial_indices["losses"] / spatial_indices["comparable_sampled_grids"].replace(0, np.nan)
        spatial_indices["net_change_prop_comparable"] = (
            spatial_indices["gains"] - spatial_indices["losses"]
        ) / spatial_indices["comparable_sampled_grids"].replace(0, np.nan)
        spatial_indices["colonisation_ratio"] = spatial_indices["gains"] / (
            spatial_indices["gains"] + spatial_indices["losses"]
        ).replace(0, np.nan)
        spatial_indices["extinction_ratio"] = spatial_indices["losses"] / (
            spatial_indices["gains"] + spatial_indices["losses"]
        ).replace(0, np.nan)

    period_tests = comparisons[[column for column in (
        "Species", "comparison", "statistical_unit",
        "kw_stat_abundance_effort", "kw_p_abundance_effort", "kw_p_abundance_effort_adjust_BH",
        "kw_stat_detection_frequency", "kw_p_detection_frequency", "kw_p_detection_frequency_adjust_BH",
        "kw_stat_relative_observation_index", "kw_p_relative_observation_index", "kw_p_relative_observation_index_adjust_BH",
        "kw_stat_occupancy", "kw_p_occupancy", "kw_p_occupancy_adjust_BH",
        "kw_stat_population_index", "kw_p_population_index", "kw_p_population_index_adjust_BH",
    ) if column in comparisons]].copy()

    interpretation = ranking[[c for c in ranking.columns if c in {
        "Species", "trend_direction", "annual_change_pct", "p_value", "inference_scope",
        "n_detection_years", "n_detection_events", "detection_span_years", "pearson_dispersion_used",
        "temporal_priority_score", "temporal_priority_rank"
    }]].copy()
    if not interpretation.empty:
        interpretation["interpretation"] = interpretation.apply(
            lambda r: (
                f"{translate_text(r.get('trend_direction', 'Sin tendencia estimable'))}; annual change "
                f"{r.get('annual_change_pct', np.nan):.2f}%; temporal priority "
                f"{r.get('temporal_priority_score', np.nan):.1f}/100."
            ), axis=1
        )
    derivative_summary = (
        predictions.groupby("Species", observed=True)
        .agg(
            derivative_mean=("annual_derivative", "mean"),
            derivative_min=("annual_derivative", "min"),
            derivative_max=("annual_derivative", "max"),
        )
        .reset_index()
        if not predictions.empty and "annual_derivative" in predictions
        else pd.DataFrame()
    )
    point_summary = (
        change_points.groupby("Species", observed=True)
        .agg(n_change_points=("change_year", "size"), first_change=("change_year", "min"), last_change=("change_year", "max"))
        .reset_index()
        if not change_points.empty else pd.DataFrame()
    )
    ranking_context = ranking.merge(
        annual_species.groupby("Species", observed=True)
        .agg(depth_median=("depth_median", "median"), habitat_dominant=("habitat_dominant", mode_or_na))
        .reset_index(), on="Species", how="left"
    )
    synthesis = ranking_context.merge(depth_trends_frame, on="Species", how="left")
    qc = pd.DataFrame(
        {
            "check": ["species", "years", "depth_records", "habitat_records", "cell_changes", "predictions"],
            "value": [table["Species"].nunique(), table["year"].nunique(), len(usable_depth), table["Habitat_aux"].notna().sum(), len(changes), len(predictions)],
            "status": ["PASS"] * 6,
        }
    )
    return {
        "control": control,
        "habitat_trace": habitat_trace,
        "annual_global": annual_global,
        "annual_species": annual_species,
        "depth_trends": depth_trends_frame,
        "habitat_period": habitat_period,
        "habitat_cell_period": habitat_cell_period,
        "cell_period": cell_period,
        "balance": balance,
        "spatial_indices": spatial_indices,
        "period_tests": period_tests,
        "interpretation": interpretation,
        "derivative_summary": derivative_summary,
        "point_summary": point_summary,
        "ranking_context": ranking_context,
        "synthesis": synthesis,
        "qc": qc,
    }


def run_temporal_analysis(
    assigned: gpd.GeoDataFrame,
    occupied_cells: gpd.GeoDataFrame,
    directories: dict[str, Path],
    settings: AnalysisSettings,
    registry: OutputRegistry,
    cartographic_context: MapContext,
    selected_grid_km: int,
) -> dict[str, Any]:
    LOGGER.info("    [6/8 · 1/4] Temporal preparation and marine-area validation")
    table = pd.DataFrame(assigned.drop(columns="geometry")).copy()
    table["grid_id"] = table["grid_id"].astype(str)
    table["Area_mar_km2"] = pd.to_numeric(
        table.get("Area_mar_km2"), errors="coerce"
    )
    invalid_area = table["Area_mar_km2"].isna() | table["Area_mar_km2"].le(0)
    if invalid_area.any():
        raise ValueError(
            "Temporal analysis requires a positive GSHHS-clipped marine surface for every assigned observation."
        )
    area_variation = table.groupby("grid_id", observed=True)["Area_mar_km2"].nunique()
    if area_variation.gt(1).any():
        raise AssertionError("The clipped marine surface is inconsistent within a grid cell.")
    table["Fecha_aux"] = pd.to_datetime(table["Fecha_aux"], errors="coerce")
    table = table.dropna(subset=["Fecha_aux"]).copy()
    table["year"] = table["Fecha_aux"].dt.year.astype(int)
    table["N_aux"] = (
        pd.to_numeric(table["N_total"], errors="coerce").fillna(0).clip(lower=0)
    )
    table["Depth_raw_temporal"] = pd.to_numeric(table["Depth"], errors="coerce")
    table["Depth_aux"] = table["Depth_raw_temporal"].where(
        table["Depth_raw_temporal"].between(0, 200, inclusive="both")
    )
    table["Habitat_aux"] = (
        table.get("Habitat", pd.Series(pd.NA, index=table.index))
        .astype("string")
        .str.strip()
    )
    table["coord_x"] = assigned.loc[table.index].geometry.x.to_numpy()
    table["coord_y"] = assigned.loc[table.index].geometry.y.to_numpy()
    periods = _periods(table, settings)
    figure_period_labels, figure_comparison_labels = _figure_label_maps(periods)
    table["period"] = _assign_period(table["Fecha_aux"], periods)

    table_dir = directories["04_tablas"] / "temporal"
    figure_dir = directories["05_figuras"] / "temporal"
    model_dir = directories["06_modelos"] / "temporal"

    LOGGER.info("    [6/8 · 2/4] Annual series, models, and period comparisons")
    annual = _annual(table.dropna(subset=["period"]))
    annual_period = _annual_period_metrics(table, periods)
    models, predictions = _fit_models(annual, settings)
    temporal_phases, change_points = _phase_segments(predictions)
    period_summary = _period_summary(table, periods, annual_period)
    comparisons = _comparisons(table, periods, period_summary, annual_period)
    changes, changes_spatial = _cell_changes(table, periods, occupied_cells)
    # Official MITECO signal and auxiliary fine-grid technical signal
    # retained only so the conservation consumer remains untouched in this phase.
    temporal_signal_official, temporal_signal_official_detail = _official_temporal_signal(
        table, periods
    )
    temporal_signal, temporal_signal_detail = _fine_temporal_signal(
        table, periods, selected_grid_km
    )
    temporal_quality = _temporal_quality_control(
        table,
        periods,
        annual_period,
        period_summary,
        comparisons,
        changes,
        temporal_signal_official,
        temporal_signal_official_detail,
    )
    ranking = _ranking(annual, comparisons, models)
    support = _temporal_support_tables(
        table.dropna(subset=["period"]), annual, periods, changes, comparisons, predictions,
        temporal_phases, change_points, ranking
    )

    period_definition = _period_definition(table, periods)
    depth_invalid_negative = int(table["Depth_raw_temporal"].lt(0).sum())
    depth_invalid_extreme = int(table["Depth_raw_temporal"].gt(200).sum())
    integrity = pd.DataFrame(
        {
            "check": [
                "n_periods",
                "records_with_period",
                "annual_rows",
                "model_rows",
                "cell_change_rows",
                "species_ranked",
                "marine_area_valid",
                "sampled_absence_universe",
                "temporal_signal_explicit",
                "invalid_negative_depth_excluded",
                "invalid_extreme_depth_excluded",
            ],
            "value": [
                len(periods),
                int(table["period"].notna().sum()),
                len(annual),
                len(models),
                len(changes),
                len(ranking),
                int((~invalid_area).sum()),
                int(changes["status"].eq("Ausencia en ambos").sum()) if not changes.empty else 0,
                int(len(temporal_signal_official)),
                depth_invalid_negative,
                depth_invalid_extreme,
            ],
            "status": [
                "PASS" if (not settings.temporal_periods or len(periods) >= 2) else "FAIL",
                "PASS" if table["period"].notna().any() else "FAIL",
                "PASS",
                "PASS",
                "PASS",
                "PASS",
                "PASS",
                "PASS",
                "PASS",
                "PASS",
                "PASS",
            ],
        }
    )
    if integrity["status"].eq("FAIL").any():
        raise AssertionError("The temporal-analysis integrity check failed.")

    LOGGER.info("    [6/8 · 3/4] Quality controls and temporal table export")
    tables = {
        "Periods": period_definition,
        "Annual_series": annual,
        "Annual_period_test_series": annual_period,
        "GLM_models": models,
        "Spline_predictions": predictions,
        "Temporal_phases": temporal_phases,
        "Change_points": change_points,
        "Period_summary": period_summary,
        "Period_comparisons": comparisons,
        "Cell_species_changes": changes,
        f"Temporal_signal_official_{selected_grid_km}km": temporal_signal_official,
        "Temporal_signal_official_components": temporal_signal_official_detail,
        "Period_statistical_tests": support["period_tests"],
        "Period_spatial_indices": support["spatial_indices"],
        "Temporal_ranking": ranking,
        "temporal_quality_control": temporal_quality,
        "Integrity_check": integrity,
    }
    book = excel_book(tables, table_dir / "Tables_20_Advanced_Temporal_Analysis.xlsx")
    registry.add(book, "20", "Complete advanced temporal-analysis workbook")
    for name, frame in tables.items():
        path = csv2(frame, table_dir / f"Table_20_{name}.csv")
        registry.add(path, "20", f"Temporal table {name.replace('_', ' ')}")

    if not changes_spatial.empty:
        gpkg = directories["02_intermedios"] / "Temporal_Cell_Species_Changes.gpkg"
        translate_geodataframe(changes_spatial).to_file(
            gpkg, layer="cell_species_changes", driver="GPKG", engine="pyogrio"
        )
        registry.add(gpkg, "20", "GeoPackage of spatial changes between periods")

    narratives: list[str] = []
    for _, row in ranking.iterrows():
        direction = translate_text(row.get("trend_direction", "Sin tendencia estimable"))
        annual_change = row.get("annual_change_pct", np.nan)
        significance = row.get("p_value", np.nan)
        signal = (
            f"{annual_change:.1f}% per year"
            if pd.notna(annual_change)
            else "not estimable"
        )
        evidence = (
            "with statistical evidence"
            if pd.notna(significance) and significance < 0.05
            else "without conclusive statistical evidence"
        )
        narratives.append(
            f"{row['Species']}: {direction.lower()} trend ({signal}; {evidence}), "
            f"temporal-priority rank {int(row['temporal_priority_rank']) if pd.notna(row['temporal_priority_rank']) else 'NA'} "
            f"and score {row['temporal_priority_score']:.1f}/100."
        )
    period_statement = (
        "No comparison between periods was performed. "
        f"The overall temporal analysis covers {periods[0].start.date()} to {periods[0].end.date()}.\n"
        if not settings.temporal_periods
        else "Periods compared: "
        + "; ".join(f"{p.label} ({p.start.date()} to {p.end.date()})" for p in periods)
        + ".\n"
    )
    narrative = (
        "ADVANCED TEMPORAL ANALYSIS\n"
        + period_statement
        + "The primary inferential trend uses a Poisson GLM on annual counts with a logarithmic offset for proxy observation events and Pearson overdispersion correction (minimum phi 1). "
        + "NB2 is used only as a sensitivity analysis when support is sufficient. Flexible curves are Poisson splines fitted to counts with the same event offset and are descriptive.\n\n"
        + "\n".join(narratives)
        + "\n\nA lack of significance does not demonstrate stability; it may reflect short series, zeros, or uneven effort."
    )
    narrative_path = text_file(
        narrative, model_dir / "Narrative_20_Results_and_Discussion.txt"
    )
    registry.add(
        narrative_path,
        "20",
        "Automatic narrative adapted to the observed results",
    )
    narrative_species = support["interpretation"].copy()
    narrative_general = pd.DataFrame(
        [{
            "section": "Results and discussion",
            "text": narrative,
            "n_species": int(table["Species"].nunique()),
            "year_min": int(table["year"].min()),
            "year_max": int(table["year"].max()),
        }]
    )
    manuscript = pd.concat(
        [
            narrative_species.assign(section="Species").rename(columns={"interpretation": "text"}),
            narrative_general[["section", "text"]],
        ],
        ignore_index=True,
        sort=False,
    )
    manuscript_path = csv2(manuscript, table_dir / "Table_20_Results_Discussion_Text.csv")
    registry.add(manuscript_path, "20", "Structured results-and-discussion text")
    model_json = model_dir / "Temporal_Models_Manifest.json"
    model_json.parent.mkdir(parents=True, exist_ok=True)
    model_json.write_text(
        json.dumps(
            {
                "periods": [
                    period.__dict__
                    | {"start": str(period.start), "end": str(period.end)}
                    for period in periods
                ],
                "settings": {"seed": settings.random_seed},
                "models": models.to_dict(orient="records"),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    registry.add(
        model_json, "20", "Machine-readable temporal-model manifest"
    )

    fig, ax = plt.subplots(figsize=(11, 6))
    sns.lineplot(
        data=annual,
        x="year",
        y="abundance_per_100_sampling_events",
        hue="Species",
        marker="o",
        ax=ax,
    )
    ax.set(
        title="Annual relative observation rate by events",
        xlabel="Year",
        ylabel="Recorded individuals per 100 proxy events",
    )
    ax.legend(title="Species", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)
    for path in save_figure(fig, figure_dir / "Figure_20_Adjusted_Annual_Series"):
        registry.add(path, "20", "Annual series standardised by proxy events")

    if not comparisons.empty:
        heat = comparisons.pivot(
            index="Species",
            columns="comparison",
            values="relative_change_abundance_pct",
        ).rename(columns=figure_comparison_labels)
        fig, ax = plt.subplots(
            figsize=(max(8, 1.8 * heat.shape[1]), max(6, 0.45 * heat.shape[0]))
        )
        limit = (
            np.nanquantile(np.abs(heat.to_numpy(dtype=float)), 0.95)
            if np.isfinite(heat.to_numpy(dtype=float)).any()
            else 1
        )
        sns.heatmap(
            heat,
            cmap="RdBu_r",
            center=0,
            vmin=-limit,
            vmax=limit,
            annot=True,
            fmt=".1f",
            ax=ax,
            cbar_kws={"label": "Effort-standardised abundance change (%)"},
        )
        ax.set(
            title="Effort-standardised abundance change between periods",
            xlabel="Comparison",
            ylabel="Species",
        )
        for path in save_figure(fig, figure_dir / "Figure_20_Changes_Between_Periods"):
            registry.add(path, "20", "Heatmap of effort-standardised changes between periods")

    fig, ax = plt.subplots(figsize=(9, max(6, 0.42 * len(ranking))))
    sns.barplot(
        data=ranking, x="temporal_priority_score", y="Species", color="#e76f51", ax=ax
    )
    ax.set(
        title="Temporal-priority ranking",
        xlabel="Score (0–100)",
        ylabel="Species",
    )
    for path in save_figure(fig, figure_dir / "Figure_20_Temporal_Priority_Ranking"):
        registry.add(path, "20", "Synthetic temporal-priority ranking")

    if not changes_spatial.empty:
        aggregate_map = (
            changes_spatial.groupby("grid_id")
            .agg(
                delta_abundance=("delta_abundance", "sum"),
                delta_annualized_density=("delta_annualized_density", "sum"),
                n_species_changed=(
                    "status",
                    lambda x: int(x.isin(["Ganancia", "Pérdida"]).sum()),
                ),
            )
            .reset_index()
        )
        geometry = (
            occupied_cells[["grid_id", "geometry"]].drop_duplicates("grid_id").copy()
        )
        geometry["grid_id"] = geometry["grid_id"].astype(str)
        map_frame = geometry.merge(aggregate_map, on="grid_id", how="inner").to_crs(
            4326
        )
        fig, ax = plt.subplots(figsize=(10, 8))
        add_map_context(ax, cartographic_context)
        limit = finite_quantile(map_frame["delta_annualized_density"].abs(), 0.95, 1)
        map_frame.plot(
            column="delta_annualized_density",
            cmap="RdBu_r",
            vmin=-limit,
            vmax=limit,
            legend=True,
            legend_kwds={"ticks": [-limit, 0, limit], "format": "%.2f"},
            linewidth=0.1,
            edgecolor="white",
            ax=ax,
            zorder=2,
        )
        map_frame_points = map_frame.copy()
        map_frame_points.geometry = map_frame_points.geometry.representative_point()
        map_frame_points.plot(
            column="delta_annualized_density", cmap="RdBu_r", vmin=-limit, vmax=limit,
            markersize=48, marker="s", edgecolor="#333333", linewidth=0.35,
            ax=ax, zorder=3,
        )
        ax.set(
            title="Aggregated annualised marine-density change",
            xlabel="Longitude",
            ylabel="Latitude",
        )
        for path in save_figure(fig, figure_dir / "Figure_20_Abundance_Change_Map"):
            registry.add(path, "20", "Aggregated annualised marine-density-change map")

        status_colors = {
            "Ganancia": "#1a9850",
            "Pérdida": "#d73027",
            "Persistencia": "#4575b4",
            "Ausencia en ambos": "#d9d9d9",
            "No comparable": "#ffffff",
        }
        map_manifest_rows: list[dict[str, Any]] = []
        map_change_dir = figure_dir / "species_change_maps"
        base_map = (
            occupied_cells[["grid_id", "geometry"]]
            .drop_duplicates("grid_id")
            .to_crs(4326)
        )
        for (species, comparison), subset in changes_spatial.groupby(
            ["Species", "comparison"], observed=True
        ):
            subset_points = subset.copy()
            subset_points.geometry = subset_points.geometry.representative_point()
            subset_points = subset_points.to_crs(4326)
            subset = subset.to_crs(4326)
            fig = plt.figure(figsize=(10.2, 7.5))
            # Keep a compact dedicated legend column on the left so symbols remain
            # unobstructed and the map itself retains a wide plotting area.
            grid = fig.add_gridspec(1, 2, width_ratios=(0.16, 0.84), wspace=0.04)
            legend_ax = fig.add_subplot(grid[0, 0])
            ax = fig.add_subplot(grid[0, 1])
            legend_ax.set_axis_off()
            add_map_context(ax, cartographic_context)
            base_map.plot(ax=ax, color="#f2f2f2", edgecolor="#bdbdbd", linewidth=0.12, zorder=1)
            plot_order = [
                "No comparable",
                "Ausencia en ambos",
                "Persistencia",
                "Pérdida",
                "Ganancia",
            ]
            marker_sizes = {
                "No comparable": 18,
                "Ausencia en ambos": 32,
                "Persistencia": 64,
                "Pérdida": 64,
                "Ganancia": 64,
            }
            marker_edges = {
                "No comparable": "#9e9e9e",
                "Ausencia en ambos": "#737373",
            }
            for order_index, status in enumerate(plot_order):
                color = status_colors[status]
                current = subset[subset["status"].eq(status)]
                current_points = subset_points[subset_points["status"].eq(status)]
                if not current.empty:
                    current.plot(
                        ax=ax, color=color, edgecolor="white", linewidth=0.15,
                        zorder=2 + order_index * 0.01,
                    )
                    current_points.plot(
                        ax=ax,
                        color=color,
                        edgecolor=marker_edges.get(status, "#333333"),
                        linewidth=0.30,
                        markersize=marker_sizes[status],
                        marker="s",
                        zorder=3 + order_index,
                    )
            ax.set(
                title=f"Spatial change · {species}\n{figure_comparison_labels.get(comparison, comparison)}",
                xlabel="Longitude",
                ylabel="Latitude",
            )
            handles = [
                Patch(facecolor=color, edgecolor="white", label=translate_text(status))
                for status, color in status_colors.items()
                if subset["status"].eq(status).any()
            ]
            legend_ax.legend(
                handles=handles,
                title="Status",
                loc="upper left",
                bbox_to_anchor=(0.00, 0.98),
                borderaxespad=0.0,
                frameon=True,
                fontsize=7,
                title_fontsize=8,
                handlelength=1.2,
                handletextpad=0.45,
                borderpad=0.45,
                labelspacing=0.35,
            )
            base_name = (
                map_change_dir
                / f"Map_20_Change_{taxon_slug(species)}_{ascii_slug(comparison)}"
            )
            output_paths = save_figure(fig, base_name)
            for path in output_paths:
                registry.add(
                    path, "20", f"Species-change map: {species}; {comparison}"
                )
            map_manifest_rows.append(
                {
                    "Species": species,
                    "comparison": comparison,
                    "png": str(output_paths[0].relative_to(directories["05_figuras"])),
                    "n_gain": int(subset["status"].eq("Ganancia").sum()),
                    "n_loss": int(subset["status"].eq("Pérdida").sum()),
                    "n_persistence": int(subset["status"].eq("Persistencia").sum()),
                    "n_absence_both": int(subset["status"].eq("Ausencia en ambos").sum()),
                    "n_non_comparable": int(subset["status"].eq("No comparable").sum()),
                    "caption": "Gain, loss, persistence and absence in both are interpreted only in cells sampled in both periods; cells lacking sampling in either period are retained as not comparable.",
                }
            )
        map_manifest = pd.DataFrame(map_manifest_rows)
        manifest_csv = csv2(
            map_manifest, table_dir / "Table_20_Species_Change_Maps_Manifest.csv"
        )
        registry.add(manifest_csv, "20", "Index and captions for species-change maps")

        status_table = changes[[c for c in (
            "grid_id", "Species", "comparison", "period_1", "period_2", "status",
            "status_union_assumption", "comparison_valid", "non_comparable_reason",
            "sampled_1", "sampled_2", "sampled_union", "sampled_intersection",
            "Area_mar_km2", "abundance_1", "abundance_2", "delta_abundance",
            "density_1", "density_2", "delta_density",
            "annualized_density_1", "annualized_density_2", "delta_annualized_density",
            "abundance_per_record_cell_1", "abundance_per_record_cell_2",
            "delta_abundance_per_record_cell"
        ) if c in changes]].copy()
        delta_table = status_table.copy()
        global_index = map_manifest.copy()
        regional_index = pd.DataFrame(columns=list(global_index.columns) + ["region"])
        recommendations = global_index.copy()
        if not recommendations.empty:
            recommendations["recommended_for_report"] = (
                recommendations[["n_gain", "n_loss", "n_persistence"]].sum(axis=1) > 0
            )
        folder_summary = pd.DataFrame(
            [{
                "cartographic_block": "20.15",
                "folder": str(map_change_dir.relative_to(directories["05_figuras"])),
                "n_maps": len(map_manifest),
                "selected_grid_km": selected_grid_km,
            }]
        )
        manifest_detail = global_index.copy()
        if not manifest_detail.empty:
            manifest_detail["exists"] = manifest_detail["png"].map(
                lambda value: (directories["05_figuras"] / value).exists()
            )
            manifest_detail["informative"] = manifest_detail[
                ["n_gain", "n_loss", "n_persistence"]
            ].sum(axis=1) > 0
        low_info = manifest_detail[~manifest_detail.get("informative", pd.Series(dtype=bool))].copy()
        caption_table = global_index[[c for c in ("Species", "comparison", "png", "caption") if c in global_index]].copy()
        caption_txt = text_file(
            "\n\n".join(caption_table.get("caption", pd.Series(dtype=str)).dropna().astype(str).tolist()),
            table_dir / "20_15J_Cartography_Figure_Captions.txt",
        )
        registry.add(caption_txt, "20", "Temporal-cartography figure captions")

    LOGGER.info("    [6/8 · 4/4] Temporal maps, figures, and narrative completed")
    return {
        "periods": periods,
        "annual": annual,
        "annual_period": annual_period,
        "models": models,
        "predictions": predictions,
        "temporal_phases": temporal_phases,
        "change_points": change_points,
        "period_summary": period_summary,
        "comparisons": comparisons,
        "cell_changes": changes,
        "temporal_signal": temporal_signal,
        "temporal_signal_detail": temporal_signal_detail,
        "temporal_signal_official": temporal_signal_official,
        "temporal_signal_official_detail": temporal_signal_official_detail,
        "spatial_indices": support["spatial_indices"],
        "period_definition": period_definition,
        "ranking": ranking,
        "integrity": integrity,
        "temporal_quality": temporal_quality,
    }
