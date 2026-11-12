"""Block 21: multicriteria prioritisation and conservation areas."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import logging
import unicodedata

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import networkx as nx
import numpy as np
import pandas as pd
import pyogrio
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.shared import Cm
from shapely import clip_by_rect, make_valid
from shapely.geometry import box

from .analysis_io import OutputRegistry, csv2, excel_book, finite_quantile, mode_or_na, save_figure, text_file
from .analysis_utils import rescale
from .cartography import MapContext, add_map_context, feature_collection
from .data import parse_dates
from .maps import render_conservation_map
from .regions import load_demarcations
from .spatial import clip_occupied_cells_with_land
from .localization import translate_frame, translate_geodataframe, translate_habitat_value, translate_text

LOGGER = logging.getLogger("hippodec_maps")


ECO_NOT_EVALUABLE = "No evaluable / evidencia ecológica insuficiente"
DATA_NOT_EVALUABLE = "No evaluable / datos insuficientes"
PRIORITY_ORDER = {ECO_NOT_EVALUABLE: -2, "Sin capacidad de discriminación": -1, "Baja": 0, "Media": 1, "Alta": 2, "Muy alta": 3}
PRIORITY_COLORS = {ECO_NOT_EVALUABLE: "#bdbdbd", "Sin capacidad de discriminación": "#969696", "Baja": "#d9d9d9", "Media": "#fee08b", "Alta": "#f46d43", "Muy alta": "#a50026"}
PROTECTED_MAP_SIMPLIFY_M = 250.0


def _normalise_field_name(value: object) -> str:
    """Return a stable ASCII key for multilingual/truncated GIS fields."""

    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return "_".join(part for part in "".join(
        character.lower() if character.isalnum() else " " for character in text
    ).split())


def _first_field(columns: Any, candidates: tuple[str, ...]) -> str | None:
    """Find the first source field matching a list of known semantic aliases."""

    lookup = {_normalise_field_name(column): str(column) for column in columns}
    for candidate in candidates:
        match = lookup.get(_normalise_field_name(candidate))
        if match is not None:
            return match
    return None


def _clip_geometries_to_marine(
    frame: gpd.GeoDataFrame | None,
    land: gpd.GeoDataFrame | None,
    marine_mask: gpd.GeoDataFrame | None = None,
) -> gpd.GeoDataFrame | None:
    """Restrict polygon layers to the official marine mask and remove land.

    The official MITECO grid is the authoritative marine extent for this run.
    The optional land subtraction remains available for runs that also provide
    GSHHG, but no replacement coastline is invented when it is absent.
    """

    if frame is None or frame.empty or frame.crs is None:
        return None if frame is None else frame.copy()
    result = frame.copy()
    projected_crs = result.crs if not result.crs.is_geographic else "EPSG:3035"
    result = result.to_crs(projected_crs)
    result = result[
        (~result.geometry.isna()) & (~result.geometry.is_empty)
    ].copy()
    if result.empty:
        return result
    result.geometry = result.geometry.map(make_valid)

    if marine_mask is not None and not marine_mask.empty and marine_mask.crs is not None:
        local_mask = marine_mask.to_crs(projected_crs)
        local_mask = local_mask[
            (~local_mask.geometry.isna()) & (~local_mask.geometry.is_empty)
        ].copy()
        if local_mask.empty:
            return result.iloc[0:0].copy()
        mask_union = make_valid(local_mask.geometry.union_all())
        result.geometry = result.geometry.intersection(mask_union)

    if land is not None and not land.empty and land.crs is not None:
        local_land = land.to_crs(projected_crs)
        local_land = local_land[
            (~local_land.geometry.isna()) & (~local_land.geometry.is_empty)
        ].copy()
        if not local_land.empty:
            local_land.geometry = local_land.geometry.map(make_valid)
            land_union = local_land.geometry.union_all()
            result.geometry = result.geometry.difference(land_union)

    result.geometry = result.geometry.map(make_valid)
    result = result[
        result.geometry.map(
            lambda geometry: geometry is not None and not geometry.is_empty
        )
    ].copy()
    return result


def _safe_mean(values: Any) -> float:
    """Return NaN explicitly when a numeric group is completely empty."""

    numeric = pd.to_numeric(pd.Series(values), errors="coerce")
    numeric = numeric.replace([np.inf, -np.inf], np.nan).dropna()
    return float(numeric.mean()) if not numeric.empty else np.nan


def _safe_median(values: Any) -> float:
    numeric = pd.to_numeric(pd.Series(values), errors="coerce")
    numeric = numeric.replace([np.inf, -np.inf], np.nan).dropna()
    return float(numeric.median()) if not numeric.empty else np.nan


def conservation_html_name(selected_grid_km: int) -> str:
    """Return the unique map name for the selected resolution."""
    resolution = int(selected_grid_km)
    if resolution <= 0:
        raise ValueError("The conservation-map resolution must be positive.")
    return f"Interactive_Priority_Conservation_Areas_Map_{resolution}km.html"


def _repair_mojibake(value: object) -> object:
    """Repair UTF-8 text read as Latin-1 without altering normal strings."""

    if value is None or pd.isna(value):
        return value
    original = str(value)
    markers = ("Ã", "Â", "â€", "ðŸ")
    if not any(marker in original for marker in markers):
        return original
    try:
        repaired = original.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return original
    before = sum(original.count(marker) for marker in markers)
    after = sum(repaired.count(marker) for marker in markers)
    return repaired if after < before else original


def _classify(values: pd.Series) -> pd.Series:
    x = pd.to_numeric(values, errors="coerce")
    valid = x.dropna()
    if valid.empty:
        return pd.Series(pd.NA, index=x.index, dtype="string")
    q50, q75, q90 = valid.quantile([0.50, 0.75, 0.90])
    return pd.Series(
        np.select([x >= q90, x >= q75, x >= q50], ["Muy alta", "Alta", "Media"], default="Baja"),
        index=x.index,
        dtype="string",
    ).mask(x.isna())



def _informative_relative_tiers(values: pd.Series) -> tuple[pd.Series, bool, dict[str, float]]:
    """Puntúa una métrica relativa sin convertir una constante en señal positiva.

    Las celdas no estimables conservan NA. Una métrica con menos de dos valores
    finitos distintos se declara no informativa y aporta 0 a todas las celdas
    estimables. Los umbrales son estrictos para que un valor constante igual al
    percentil nunca se convierta en evidencia.
    """

    x = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan)
    score = pd.Series(np.nan, index=x.index, dtype=float)
    valid = x.dropna()
    if valid.empty:
        return score, False, {"q50": np.nan, "q75": np.nan, "q90": np.nan}
    if valid.nunique(dropna=True) < 2:
        score.loc[x.notna()] = 0.0
        value = float(valid.iloc[0])
        return score, False, {"q50": value, "q75": value, "q90": value}
    q50, q75, q90 = [float(v) for v in valid.quantile([0.50, 0.75, 0.90])]
    score.loc[x.notna()] = np.select(
        [x.loc[x.notna()].gt(q90), x.loc[x.notna()].gt(q75), x.loc[x.notna()].gt(q50)],
        [100.0, 75.0, 40.0],
        default=0.0,
    )
    return score, True, {"q50": q50, "q75": q75, "q90": q90}


def _classify_fixed_priority(
    score: pd.Series,
    evaluable: pd.Series,
    discriminating: pd.Series | bool,
    strong_families: pd.Series,
    active_families: pd.Series,
) -> pd.Series:
    """Clases fijas: no fuerzan un porcentaje de celdas a prioridad alta."""

    x = pd.to_numeric(score, errors="coerce")
    eval_mask = pd.Series(evaluable, index=x.index).fillna(False).astype(bool)
    if isinstance(discriminating, pd.Series):
        discr = discriminating.reindex(x.index).fillna(False).astype(bool)
    else:
        discr = pd.Series(bool(discriminating), index=x.index)
    strong = pd.to_numeric(strong_families, errors="coerce").fillna(0)
    active = pd.to_numeric(active_families, errors="coerce").fillna(0)
    out = pd.Series("Baja", index=x.index, dtype="string")
    out.loc[~eval_mask] = ECO_NOT_EVALUABLE
    out.loc[eval_mask & ~discr] = "Sin capacidad de discriminación"
    valid = eval_mask & discr & x.notna()
    out.loc[valid & x.ge(35)] = "Media"
    out.loc[valid & x.ge(65) & strong.ge(1) & active.ge(1)] = "Alta"
    out.loc[valid & x.ge(85) & strong.ge(2) & active.ge(2)] = "Muy alta"
    return out


def _observation_support_by_cell(assigned: gpd.GeoDataFrame) -> pd.DataFrame:
    """Recompute support and basic biological metrics from assigned observations.

    For conservation these observation-derived metrics are authoritative, preventing
    stale or incomplete temporal coverage from intermediate tables from affecting
    prioritisation.
    """

    if assigned is None or assigned.empty or "grid_id" not in assigned.columns:
        return pd.DataFrame(columns=["master_id"])
    work = pd.DataFrame(assigned.drop(columns="geometry", errors="ignore")).copy()
    work["master_id"] = work["grid_id"].astype(str)
    work["_depth_valid"] = pd.to_numeric(work.get("Depth"), errors="coerce").notna()
    habitat = work.get("Habitat", pd.Series(pd.NA, index=work.index, dtype="string")).astype("string").str.strip()
    work["_habitat_valid"] = habitat.notna() & habitat.ne("") & ~habitat.str.lower().isin(["nan", "none", "na", "n/a"])
    if "Observer" in work.columns:
        observer = work["Observer"].astype("string").str.strip()
        work["_observer_valid"] = observer.notna() & observer.ne("") & ~observer.str.lower().isin(["nan", "none", "na", "n/a"])
        work["_observer_value"] = observer.where(work["_observer_valid"])
    else:
        work["_observer_valid"] = False
        work["_observer_value"] = pd.NA

    if "sampling_event_id" in work.columns:
        event = work["sampling_event_id"].astype("string").str.strip()
        missing = event.isna() | event.eq("")
        event = event.mask(missing, "row-" + work.index.astype(str))
    elif "obs_id" in work.columns:
        event = work["obs_id"].astype("string").str.strip()
        missing = event.isna() | event.eq("")
        event = event.mask(missing, "row-" + work.index.astype(str))
    else:
        event = pd.Series("row-" + work.index.astype(str), index=work.index, dtype="string")
    work["_event"] = event

    date = None
    for candidate in ("Fecha_aux", "Date of observation", "Fecha de observación"):
        if candidate in work.columns:
            date = parse_dates(work[candidate])
            break
    if date is None:
        date = pd.Series(pd.NaT, index=work.index)
    work["_year"] = date.dt.year

    species = work.get("Species", work.get("Especie", pd.Series(pd.NA, index=work.index, dtype="string"))).astype("string").str.strip()
    work["_species"] = species.where(species.notna() & species.ne(""))
    abundance_col = next((candidate for candidate in ("N_total", "n_total", "Abundance", "abundance") if candidate in work.columns), None)
    if abundance_col is None:
        work["_abundance"] = 1.0
    else:
        abundance = pd.to_numeric(work[abundance_col], errors="coerce")
        work["_abundance"] = abundance.where(abundance.notna(), 1.0).clip(lower=0)

    rows=[]
    for master_id, group in work.groupby("master_id", observed=True):
        observer_available = bool(group["_observer_valid"].any())
        valid_years = group["_year"].dropna()
        valid_species = group["_species"].dropna()
        rows.append({
            "master_id": str(master_id),
            "support_records_from_assigned": int(len(group)),
            "support_n_sampling_events": int(group["_event"].nunique()),
            "support_n_years_observed": int(valid_years.nunique()) if not valid_years.empty else np.nan,
            "support_richness": int(valid_species.nunique()) if not valid_species.empty else np.nan,
            "support_abundance": float(group["_abundance"].sum()),
            "n_observers_support": int(group["_observer_value"].dropna().nunique()) if observer_available else np.nan,
            "n_depth_valid_support": int(group["_depth_valid"].sum()),
            "n_habitat_valid_support": int(group["_habitat_valid"].sum()),
        })
    return pd.DataFrame(rows)


def _numeric_column(frame: pd.DataFrame, name: str) -> pd.Series:
    if name not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[name], errors="coerce")


def _coalesce_numeric(primary: pd.Series, fallback: pd.Series) -> pd.Series:
    """Numeric combine-first with explicit dtype semantics."""
    index = primary.index.union(fallback.index)
    left = pd.to_numeric(primary.reindex(index), errors="coerce")
    right = pd.to_numeric(fallback.reindex(index), errors="coerce")
    return left.where(left.notna(), right)


def _component_fraction(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    num = pd.to_numeric(numerator, errors="coerce")
    den = pd.to_numeric(denominator, errors="coerce")
    out = pd.Series(np.nan, index=num.index, dtype=float)
    valid = num.notna() & den.gt(0)
    out.loc[valid] = (num.loc[valid] / den.loc[valid]).clip(0, 1)
    return out


def _rare_representation_support(assigned: gpd.GeoDataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    """Summarise repeated representation of low-occupancy species in this run.

    Rarity is relative to the analysed dataset and does not replace legal or threat
    status. A species is treated as low-occupancy when it occurs in <=10% of planning
    units with data. A single record never creates conservation priority: the species
    must occur in at least two independent sampling events within the unit.
    """

    empty = pd.DataFrame(columns=[
        "master_id", "n_low_occupancy_species_repeated", "max_low_occupancy_species_events",
        "max_low_occupancy_species_years", "low_occupancy_species_repeated",
    ])
    diagnostics = {
        "low_occupancy_threshold_cells": np.nan,
        "n_low_occupancy_species": 0,
    }
    if assigned is None or assigned.empty or not {"grid_id", "Species"}.issubset(assigned.columns):
        return empty, diagnostics

    work = pd.DataFrame(assigned.drop(columns="geometry", errors="ignore")).copy()
    work["grid_id"] = work["grid_id"].astype(str)
    work["Species"] = work["Species"].astype("string").str.strip()
    work = work[work["Species"].notna() & work["Species"].ne("")].copy()
    if work.empty:
        return empty, diagnostics

    if "sampling_event_id" in work.columns:
        event = work["sampling_event_id"].astype("string").str.strip()
        missing = event.isna() | event.eq("")
        event = event.mask(missing, "row-" + work.index.astype(str))
    elif "obs_id" in work.columns:
        event = work["obs_id"].astype("string").str.strip()
        missing = event.isna() | event.eq("")
        event = event.mask(missing, "row-" + work.index.astype(str))
    else:
        event = pd.Series("row-" + work.index.astype(str), index=work.index, dtype="string")
    work["_event"] = event

    date = None
    for candidate in ("Fecha_aux", "Date of observation", "Fecha de observación"):
        if candidate in work.columns:
            date = parse_dates(work[candidate])
            break
    if date is None:
        date = pd.Series(pd.NaT, index=work.index)
    work["_year"] = date.dt.year

    by_cell_species = (
        work.groupby(["grid_id", "Species"], observed=True)
        .agg(
            species_events=("_event", "nunique"),
            species_years=("_year", lambda values: int(pd.Series(values).dropna().nunique())),
        )
        .reset_index()
    )
    n_cells = int(work["grid_id"].nunique())
    if n_cells <= 0 or by_cell_species.empty:
        return empty, diagnostics
    occupancy = by_cell_species.groupby("Species", observed=True)["grid_id"].nunique()
    threshold = max(1, int(np.ceil(0.10 * n_cells)))
    low_occupancy_species = set(occupancy[occupancy.le(threshold)].index.astype(str))
    diagnostics = {
        "low_occupancy_threshold_cells": float(threshold),
        "n_low_occupancy_species": int(len(low_occupancy_species)),
    }
    if not low_occupancy_species:
        return empty, diagnostics

    repeated = by_cell_species[
        by_cell_species["Species"].astype(str).isin(low_occupancy_species)
        & by_cell_species["species_events"].ge(2)
    ].copy()
    if repeated.empty:
        return empty, diagnostics

    rows = []
    for grid_id, group in repeated.groupby("grid_id", observed=True):
        rows.append({
            "master_id": str(grid_id),
            "n_low_occupancy_species_repeated": int(group["Species"].nunique()),
            "max_low_occupancy_species_events": int(pd.to_numeric(group["species_events"], errors="coerce").max()),
            "max_low_occupancy_species_years": int(pd.to_numeric(group["species_years"], errors="coerce").max()),
            "low_occupancy_species_repeated": " | ".join(sorted(group["Species"].astype(str).unique())),
        })
    return pd.DataFrame(rows), diagnostics


def _population_stronghold_support(assigned: gpd.GeoDataFrame) -> pd.DataFrame:
    """Summarise persistent species-level occurrence cores by planning unit.

    A moderate core requires the same species in >=3 years, >=8 independent
    sampling events and >=8 accumulated individuals. A strong core requires
    >=4 years, >=12 events and >=12 individuals. These are biological evidence
    rules, not sampling-adequacy filters: a qualifying core is an alternative
    conservation pathway for species-poor but repeatedly occupied sites.
    """
    columns = [
        "master_id", "n_population_core_species", "n_strong_population_core_species",
        "max_population_core_events", "max_population_core_years",
        "max_population_core_abundance", "population_core_species",
        "strong_population_core_species",
    ]
    empty = pd.DataFrame(columns=columns)
    if assigned is None or assigned.empty or "grid_id" not in assigned.columns or "Species" not in assigned.columns:
        return empty

    work = assigned.copy()
    work["grid_id"] = work["grid_id"].astype(str)
    work["Species"] = work["Species"].astype("string").str.strip()
    work = work[work["Species"].notna() & work["Species"].ne("")].copy()
    if work.empty:
        return empty

    if "sampling_event_id" in work.columns:
        event = work["sampling_event_id"].astype("string").str.strip()
        missing = event.isna() | event.eq("")
        event = event.mask(missing, "row-" + work.index.astype(str))
    elif "obs_id" in work.columns:
        event = work["obs_id"].astype("string").str.strip()
        missing = event.isna() | event.eq("")
        event = event.mask(missing, "row-" + work.index.astype(str))
    else:
        event = pd.Series("row-" + work.index.astype(str), index=work.index, dtype="string")
    work["_event"] = event

    date = None
    for candidate in ("Fecha_aux", "Date of observation", "Fecha de observación"):
        if candidate in work.columns:
            date = parse_dates(work[candidate])
            break
    if date is None:
        date = pd.Series(pd.NaT, index=work.index)
    work["_year"] = date.dt.year

    abundance_col = None
    for candidate in ("N_total", "n_total", "Abundance", "abundance"):
        if candidate in work.columns:
            abundance_col = candidate
            break
    if abundance_col is None:
        work["_abundance"] = 1.0
    else:
        abundance = pd.to_numeric(work[abundance_col], errors="coerce")
        # Presence records with missing abundance count conservatively as one individual.
        work["_abundance"] = abundance.where(abundance.notna(), 1.0).clip(lower=0)

    by_species = (
        work.groupby(["grid_id", "Species"], observed=True)
        .agg(
            species_events=("_event", "nunique"),
            species_years=("_year", lambda values: int(pd.Series(values).dropna().nunique())),
            species_abundance=("_abundance", "sum"),
        )
        .reset_index()
    )
    by_species["population_core_moderate"] = (
        by_species["species_years"].ge(3)
        & by_species["species_events"].ge(8)
        & by_species["species_abundance"].ge(8)
    )
    by_species["population_core_strong"] = (
        by_species["species_years"].ge(4)
        & by_species["species_events"].ge(12)
        & by_species["species_abundance"].ge(12)
    )
    core = by_species[by_species["population_core_moderate"]].copy()
    if core.empty:
        return empty

    rows = []
    for grid_id, group in core.groupby("grid_id", observed=True):
        strong = group[group["population_core_strong"]]
        rows.append({
            "master_id": str(grid_id),
            "n_population_core_species": int(group["Species"].nunique()),
            "n_strong_population_core_species": int(strong["Species"].nunique()),
            "max_population_core_events": int(pd.to_numeric(group["species_events"], errors="coerce").max()),
            "max_population_core_years": int(pd.to_numeric(group["species_years"], errors="coerce").max()),
            "max_population_core_abundance": float(pd.to_numeric(group["species_abundance"], errors="coerce").max()),
            "population_core_species": " | ".join(sorted(group["Species"].astype(str).unique())),
            "strong_population_core_species": " | ".join(sorted(strong["Species"].astype(str).unique())),
        })
    return pd.DataFrame(rows, columns=columns)


def _evidence_priority_class(
    score: pd.Series,
    evaluable: pd.Series,
    discriminating: pd.Series | bool,
    active_families: pd.Series,
    strong_families: pd.Series,
    biodiversity_anchor: pd.Series,
    persistence_anchor: pd.Series,
    n_events: pd.Series,
    abundance: pd.Series,
) -> pd.Series:
    """Classify priority using explicit multiple-evidence requirements.

    No single family, including LCBD, can create High priority. High requires at
    least three active families plus a biodiversity anchor (richness or repeated
    representation of low-occupancy species). Very high requires all four families
    active and at least three at strong level.
    """

    x = pd.to_numeric(score, errors="coerce")
    eval_mask = pd.Series(evaluable, index=x.index).fillna(False).astype(bool)
    if isinstance(discriminating, pd.Series):
        discr = discriminating.reindex(x.index).fillna(False).astype(bool)
    else:
        discr = pd.Series(bool(discriminating), index=x.index)
    active = pd.to_numeric(active_families, errors="coerce").fillna(0)
    strong = pd.to_numeric(strong_families, errors="coerce").fillna(0)
    anchor = pd.Series(biodiversity_anchor, index=x.index).fillna(False).astype(bool)
    persistence = pd.Series(persistence_anchor, index=x.index).fillna(False).astype(bool)
    events = pd.to_numeric(n_events, errors="coerce")
    abundance_support = pd.to_numeric(abundance, errors="coerce")

    out = pd.Series("Baja", index=x.index, dtype="string")
    out.loc[~eval_mask] = ECO_NOT_EVALUABLE
    out.loc[eval_mask & ~discr] = "Sin capacidad de discriminación"
    valid = eval_mask & discr & x.notna()
    out.loc[valid & x.ge(37.5) & active.ge(2)] = "Media"
    out.loc[
        valid & anchor & persistence & events.ge(6) & abundance_support.ge(6)
        & x.ge(62.5) & active.ge(3)
    ] = "Alta"
    out.loc[
        valid & anchor & persistence & events.ge(12) & abundance_support.ge(12)
        & x.ge(87.5) & active.ge(4) & strong.ge(3)
    ] = "Muy alta"
    return out


def _build_priority_products(
    priority: gpd.GeoDataFrame,
    assigned: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame, dict[str, float | bool]]:
    """Build conservation priority from convergent biological evidence.

    Priority is no longer derived from LCBD + richness. It uses three transparent
    pathways: convergence of four biological-evidence families (local richness,
    temporal persistence, repeated use and repeated representation of low-occupancy
    species), persistent occurrence cores of a species, and diversity cores. LCBD is
    retained as a community-uniqueness descriptor but can never create a priority area
    by itself. Data adequacy and temporal monitoring remain separate products.
    """

    out = priority.copy()
    support = _observation_support_by_cell(assigned)
    if not support.empty:
        out = out.merge(support, on="master_id", how="left", validate="one_to_one")
        out = gpd.GeoDataFrame(out, geometry="geometry", crs=priority.crs)
    for column in (
        "support_records_from_assigned", "support_n_sampling_events", "support_n_years_observed",
        "support_richness", "support_abundance", "n_observers_support",
        "n_depth_valid_support", "n_habitat_valid_support",
    ):
        if column not in out:
            out[column] = np.nan

    rare_support, rare_diagnostics = _rare_representation_support(assigned)
    if not rare_support.empty:
        out = out.merge(rare_support, on="master_id", how="left", validate="one_to_one")
        out = gpd.GeoDataFrame(out, geometry="geometry", crs=priority.crs)
    for column, default in (
        ("n_low_occupancy_species_repeated", 0),
        ("max_low_occupancy_species_events", 0),
        ("max_low_occupancy_species_years", 0),
        ("low_occupancy_species_repeated", ""),
    ):
        if column not in out:
            out[column] = default
    for column in ("n_low_occupancy_species_repeated", "max_low_occupancy_species_events", "max_low_occupancy_species_years"):
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0)
    out["low_occupancy_species_repeated"] = out["low_occupancy_species_repeated"].fillna("").astype(str)

    population_support = _population_stronghold_support(assigned)
    if not population_support.empty:
        out = out.merge(population_support, on="master_id", how="left", validate="one_to_one")
        out = gpd.GeoDataFrame(out, geometry="geometry", crs=priority.crs)
    for column, default in (
        ("n_population_core_species", 0),
        ("n_strong_population_core_species", 0),
        ("max_population_core_events", 0),
        ("max_population_core_years", 0),
        ("max_population_core_abundance", 0.0),
        ("population_core_species", ""),
        ("strong_population_core_species", ""),
    ):
        if column not in out:
            out[column] = default
    for column in ("n_population_core_species", "n_strong_population_core_species", "max_population_core_events", "max_population_core_years", "max_population_core_abundance"):
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0)
    out["population_core_species"] = out["population_core_species"].fillna("").astype(str)
    out["strong_population_core_species"] = out["strong_population_core_species"].fillna("").astype(str)

    # Conservation uses metrics recomputed directly from assigned observations whenever
    # available; intermediate grid attributes are only fallbacks.
    richness = _coalesce_numeric(_numeric_column(out, "support_richness"), _numeric_column(out, "richness"))
    n_events = _coalesce_numeric(_numeric_column(out, "support_n_sampling_events"), _numeric_column(out, "n_sampling_events"))
    n_years = _coalesce_numeric(_numeric_column(out, "support_n_years_observed"), _numeric_column(out, "n_years_observed"))
    abundance = _coalesce_numeric(_numeric_column(out, "support_abundance"), _numeric_column(out, "abundance"))
    n_scales = _numeric_column(out, "n_scales_evaluable")
    n_records = _coalesce_numeric(_numeric_column(out, "support_records_from_assigned"), _numeric_column(out, "n_records"))
    out["richness"] = richness
    out["n_sampling_events"] = n_events
    out["n_years_observed"] = n_years
    out["abundance"] = abundance
    out["n_records"] = n_records
    n_depth = _coalesce_numeric(_numeric_column(out, "n_depth_valid_support"), _numeric_column(out, "n_depth_valid"))
    n_habitat = _numeric_column(out, "n_habitat_valid_support")
    n_observers = _numeric_column(out, "n_observers_support")
    if "n_temporal_sampling_events" in out.columns:
        n_temporal = _numeric_column(out, "n_temporal_sampling_events")
    else:
        n_temporal = _numeric_column(out, "n_temporal_records")

    # Four evidence families. Levels are 0=absent, 1=moderate, 2=strong.
    richness_level = pd.Series(
        np.select([richness.ge(3), richness.ge(2)], [2, 1], default=0),
        index=out.index, dtype=int,
    )
    persistence_level = pd.Series(
        np.select([n_years.ge(3), n_years.ge(2)], [2, 1], default=0),
        index=out.index, dtype=int,
    )
    repeated_use_level = pd.Series(
        np.select(
            [(n_events.ge(10) & abundance.ge(10)), (n_events.ge(4) & abundance.ge(4))],
            [2, 1], default=0,
        ),
        index=out.index, dtype=int,
    )
    rare_level = pd.Series(
        np.select(
            [
                out["n_low_occupancy_species_repeated"].ge(2)
                | out["max_low_occupancy_species_years"].ge(3)
                | out["max_low_occupancy_species_events"].ge(5),
                out["n_low_occupancy_species_repeated"].ge(1),
            ],
            [2, 1], default=0,
        ),
        index=out.index, dtype=int,
    )

    out["ecological_richness_family_score"] = richness_level.astype(float) * 50.0
    out["ecological_persistence_family_score"] = persistence_level.astype(float) * 50.0
    out["ecological_repeated_use_family_score"] = repeated_use_level.astype(float) * 50.0
    out["ecological_low_occupancy_representation_family_score"] = rare_level.astype(float) * 50.0

    family_levels = pd.DataFrame({
        "richness": richness_level,
        "persistence": persistence_level,
        "repeated_use": repeated_use_level,
        "low_occupancy_representation": rare_level,
    }, index=out.index)
    out["evidence_family_richness_active"] = richness_level.ge(1)
    out["evidence_family_persistence_active"] = persistence_level.ge(1)
    out["evidence_family_repeated_use_active"] = repeated_use_level.ge(1)
    out["evidence_family_low_occupancy_active"] = rare_level.ge(1)
    out["evidence_family_richness_strong"] = richness_level.eq(2)
    out["evidence_family_persistence_strong"] = persistence_level.eq(2)
    out["evidence_family_repeated_use_strong"] = repeated_use_level.eq(2)
    out["evidence_family_low_occupancy_strong"] = rare_level.eq(2)
    out["n_independent_ecological_families_active"] = family_levels.ge(1).sum(axis=1).astype(int)
    out["n_independent_ecological_families_strong"] = family_levels.eq(2).sum(axis=1).astype(int)
    biodiversity_anchor = richness_level.ge(1) | rare_level.ge(1)
    out["biodiversity_anchor"] = biodiversity_anchor

    # Three explicit conservation pathways share one transparent 0-100 index.
    # The convergent-family score is retained separately. Persistent single-species
    # occurrence cores and well-supported diversity cores provide alternative routes
    # to High priority, without allowing an isolated observation to define a zone.
    out["ecological_convergent_evidence_score"] = family_levels.mean(axis=1) * 50.0
    population_core = out["n_population_core_species"].ge(1)
    strong_population_core = out["n_strong_population_core_species"].ge(1)
    out["ecological_population_core_score"] = np.select(
        [strong_population_core, population_core], [75.0, 62.5], default=0.0
    )

    # Diversity-core pathway. A multi-year diversity core requires >=4 species,
    # >=2 observed years and >=5 independent sampling events. An exceptional
    # diversity concentration can qualify with one year only when evidence is much
    # stronger: >=5 species, >=10 independent events and repeated representation
    # of >=2 low-occupancy species. The latter is flagged for temporal validation.
    diversity_core_multiyear = richness.ge(4) & n_years.ge(2) & n_events.ge(5)
    exceptional_diversity_evidence = (
        richness.ge(5)
        & n_events.ge(12)
        & out["n_low_occupancy_species_repeated"].ge(2)
    )
    # Mark as "exceptional" only when this pathway is actually needed because
    # multi-year support is not yet available. Multi-year sites are classified
    # through the ordinary diversity-core route and do not receive a temporal warning.
    diversity_core_exceptional = exceptional_diversity_evidence & ~diversity_core_multiyear
    diversity_core = diversity_core_multiyear | diversity_core_exceptional
    strong_diversity_core = (
        richness.ge(5) & n_years.ge(3) & n_events.ge(10)
    ) | (
        richness.ge(6)
        & n_events.ge(15)
        & out["n_low_occupancy_species_repeated"].ge(2)
    )
    out["ecological_diversity_core_score"] = np.select(
        [strong_diversity_core, diversity_core], [75.0, 62.5], default=0.0
    )
    out["ecological_priority_score"] = np.maximum.reduce([
        out["ecological_convergent_evidence_score"].to_numpy(dtype=float),
        out["ecological_population_core_score"].astype(float),
        out["ecological_diversity_core_score"].astype(float),
    ])

    # LCBD and raw abundance are retained only as context, never as selection gates.
    lcbd_tier, lcbd_informative, lcbd_q = _informative_relative_tiers(_numeric_column(out, "LCBD"))
    abundance_tier, abundance_informative, abundance_q = _informative_relative_tiers(np.log1p(abundance.clip(lower=0)))
    out["ecological_lcbd_context_score"] = lcbd_tier
    out["ecological_abundance_context_score"] = abundance_tier

    ecological_evaluable = richness.notna() | n_years.notna() | n_events.notna() | abundance.notna()
    ecological_discriminating = any(family_levels[column].nunique(dropna=True) >= 2 for column in family_levels.columns)
    cell_discriminating = pd.Series(bool(ecological_discriminating), index=out.index) & ecological_evaluable
    convergence_class = _evidence_priority_class(
        out["ecological_convergent_evidence_score"], ecological_evaluable, cell_discriminating,
        out["n_independent_ecological_families_active"], out["n_independent_ecological_families_strong"],
        biodiversity_anchor, persistence_level.ge(1), n_events, abundance,
    )
    out["ecological_priority_class"] = convergence_class.copy()
    convergence_high = convergence_class.isin(["Alta", "Muy alta"])
    # Alternative pathways for evidence patterns that a single convergence rule would
    # otherwise miss: persistent single-species occurrence cores and diversity cores.
    # Both require repeated support; an isolated observation can never qualify.
    base_low = ~out["ecological_priority_class"].isin(["Alta", "Muy alta"])
    out.loc[ecological_evaluable & population_core & base_low, "ecological_priority_class"] = "Alta"
    base_low = ~out["ecological_priority_class"].isin(["Alta", "Muy alta"])
    out.loc[ecological_evaluable & diversity_core & base_low, "ecological_priority_class"] = "Alta"
    out["population_core_pathway"] = population_core
    out["strong_population_core_pathway"] = strong_population_core
    out["diversity_core_pathway"] = diversity_core
    out["strong_diversity_core_pathway"] = strong_diversity_core
    out["exceptional_diversity_core_pathway"] = diversity_core_exceptional
    out["ecological_priority_scope"] = "conservation priority based on convergent evidence within the current run"
    out["ecological_priority_evaluable"] = ecological_evaluable
    out["ecological_priority_discriminating"] = cell_discriminating

    # Data adequacy remains independent from ecological priority.
    components = pd.DataFrame(index=out.index)
    components["events"] = (n_events / 10.0).clip(0, 1)
    components["years"] = (n_years / 5.0).clip(0, 1)
    components["scales"] = (n_scales / 3.0).clip(0, 1)
    components["observers"] = (n_observers / 3.0).clip(0, 1)
    components["depth_coverage"] = _component_fraction(n_depth, n_records)
    components["habitat_coverage"] = _component_fraction(n_habitat, n_records)
    components["temporal_coverage"] = _component_fraction(n_temporal, n_events)
    out["data_adequacy_n_components"] = components.notna().sum(axis=1).astype(int)
    out["data_adequacy_score"] = components.mean(axis=1, skipna=True) * 100.0
    support_ok = n_events.ge(2).fillna(False)
    adequacy_evaluable = support_ok & out["data_adequacy_n_components"].ge(3)
    out["data_adequacy_class"] = pd.Series(
        np.select(
            [
                adequacy_evaluable & out["data_adequacy_score"].ge(75),
                adequacy_evaluable & out["data_adequacy_score"].ge(50),
                adequacy_evaluable & out["data_adequacy_score"].ge(25),
                adequacy_evaluable,
            ],
            ["Alta", "Media", "Baja", "Muy baja"],
            default=DATA_NOT_EVALUABLE,
        ),
        index=out.index, dtype="string",
    )

    # Monitoring remains a separate temporal product.
    temporal_raw = pd.to_numeric(out.get("temporal_signal_raw", pd.Series(np.nan, index=out.index)), errors="coerce").clip(0, 1)
    temporal_evaluable = temporal_raw.notna() & n_temporal.gt(0)
    out["monitoring_priority_score"] = temporal_raw * 100.0
    out["monitoring_priority_class"] = pd.Series(
        np.select(
            [
                temporal_evaluable & out["monitoring_priority_score"].ge(75),
                temporal_evaluable & out["monitoring_priority_score"].ge(50),
                temporal_evaluable & out["monitoring_priority_score"].ge(25),
                temporal_evaluable,
            ],
            ["Muy alta", "Alta", "Media", "Baja"],
            default=DATA_NOT_EVALUABLE,
        ), index=out.index, dtype="string",
    )

    # Sensitivity scenarios change weights, but retain the same multi-family gates.
    scenario_specs = {
        "balanced": {"richness": 0.25, "persistence": 0.25, "repeated_use": 0.25, "low_occupancy_representation": 0.25},
        "biodiversity_focus": {"richness": 0.35, "persistence": 0.20, "repeated_use": 0.10, "low_occupancy_representation": 0.35},
        "persistence_focus": {"richness": 0.20, "persistence": 0.35, "repeated_use": 0.30, "low_occupancy_representation": 0.15},
    }
    scenario_classes = []
    for name, weights in scenario_specs.items():
        convergent_score = sum(family_levels[key].astype(float) * 50.0 * weight for key, weight in weights.items())
        score = np.maximum.reduce([
            convergent_score.to_numpy(dtype=float),
            out["ecological_population_core_score"].to_numpy(dtype=float),
            out["ecological_diversity_core_score"].to_numpy(dtype=float),
        ])
        out[f"ecological_priority_score_{name}"] = score
        cls = _evidence_priority_class(
            convergent_score, ecological_evaluable, cell_discriminating,
            out["n_independent_ecological_families_active"], out["n_independent_ecological_families_strong"],
            biodiversity_anchor, persistence_level.ge(1), n_events, abundance,
        )
        cls.loc[ecological_evaluable & population_core & ~cls.isin(["Alta", "Muy alta"])] = "Alta"
        cls.loc[ecological_evaluable & diversity_core & ~cls.isin(["Alta", "Muy alta"])] = "Alta"
        out[f"ecological_priority_class_{name}"] = cls
        scenario_classes.append(f"ecological_priority_class_{name}")
    out["n_scenarios_high_priority"] = out[scenario_classes].isin(["Alta", "Muy alta"]).sum(axis=1).astype(int)
    out["n_escenarios_prioridad_alta"] = out["n_scenarios_high_priority"]
    out["sensitivity_class"] = pd.Series(
        np.select(
            [
                ~ecological_evaluable,
                ecological_evaluable & ~cell_discriminating,
                out["n_scenarios_high_priority"].eq(3),
                out["n_scenarios_high_priority"].eq(2),
                out["n_scenarios_high_priority"].eq(1),
            ],
            ["No aplicable", "Sin capacidad de discriminación", "Estable en 3 escenarios ecológicos", "Estable en 2 escenarios ecológicos", "Sensible a ponderación ecológica"],
            default="No alta en escenarios ecológicos",
        ), index=out.index, dtype="string",
    )

    out["strong_ecological_criterion"] = out["n_independent_ecological_families_strong"].ge(1)
    out["evidence_lcbd_context_high"] = pd.to_numeric(out["ecological_lcbd_context_score"], errors="coerce").ge(75)
    out["evidence_temporal_high"] = out["monitoring_priority_score"].ge(75) & temporal_evaluable

    def justification(row: pd.Series) -> str:
        state = str(row["ecological_priority_class"])
        if state == ECO_NOT_EVALUABLE:
            return "Ecological priority is not evaluable because no biological metrics can be estimated for this planning unit."
        if state == "Sin capacidad de discriminación":
            return "The available biological metrics do not discriminate among the evaluable planning units in this run."
        pathway = str(row.get("ecological_priority_pathway_code", "not_selected"))
        if pathway == "convergence":
            active = []
            if bool(row["evidence_family_richness_active"]): active.append("species richness")
            if bool(row["evidence_family_persistence_active"]): active.append("temporal persistence")
            if bool(row["evidence_family_repeated_use_active"]): active.append("repeated use")
            if bool(row["evidence_family_low_occupancy_active"]): active.append("repeated representation of low-occupancy species in the dataset")
            public_state = translate_text(state)
            return f"{public_state} ecological priority through convergent biological evidence: " + ", ".join(active) + "."
        if pathway == "persistent_occurrence_and_diversity" and state == "Alta":
            species = str(row.get("population_core_species", "")).strip()
            core = f" ({species})" if species else ""
            return f"High ecological priority through two concurrent alternative pathways: a persistent occurrence core{core} and a diversity core; both have repeated support and neither depends on a single isolated observation."
        if pathway == "persistent_occurrence" and state == "Alta":
            species = str(row.get("population_core_species", "")).strip()
            core = f" for {species}" if species else ""
            return f"High ecological priority through a persistent occurrence core{core}, supported by repeated presence across multiple years and independent events."
        if pathway == "exceptional_diversity" and state == "Alta":
            return "High ecological priority through an exceptional diversity concentration: high richness and repeated representation of low-occupancy species, with temporal validation prioritised."
        if pathway == "diversity_core" and state == "Alta":
            return "High ecological priority through a multi-year diversity core, supported by at least four species, two years and five independent events."
        active = []
        if bool(row["evidence_family_richness_active"]):
            active.append("species richness")
        if bool(row["evidence_family_persistence_active"]):
            active.append("temporal persistence")
        if bool(row["evidence_family_repeated_use_active"]):
            active.append("repeated use")
        if bool(row["evidence_family_low_occupancy_active"]):
            active.append("repeated representation of low-occupancy species in the dataset")
        if not active:
            return "Low ecological priority; insufficient biological-evidence families converge."
        public_state = translate_text(state).lower()
        return f"{public_state.capitalize()} ecological priority supported by " + ", ".join(active) + "."

    out["_convergence_priority_class"] = convergence_class.astype("string")
    final_high = out["ecological_priority_class"].isin(["Alta", "Muy alta"])
    convergence_selected = convergence_class.isin(["Alta", "Muy alta"])
    population_promoted = final_high & ~convergence_selected & population_core
    diversity_promoted = final_high & ~convergence_selected & diversity_core
    concurrent_alternative = population_promoted & diversity_promoted
    pathway_code = np.select(
        [
            convergence_selected,
            concurrent_alternative,
            population_promoted,
            diversity_promoted & diversity_core_exceptional,
            diversity_promoted,
        ],
        [
            "convergence",
            "persistent_occurrence_and_diversity",
            "persistent_occurrence",
            "exceptional_diversity",
            "diversity_core",
        ],
        default="not_selected",
    )
    out["ecological_priority_pathway_code"] = pd.Series(pathway_code, index=out.index, dtype="string")
    out["ecological_priority_pathway"] = out["ecological_priority_pathway_code"].map({
        "convergence": "Convergent biological evidence",
        "persistent_occurrence_and_diversity": "Concurrent persistent occurrence and diversity core",
        "persistent_occurrence": "Persistent occurrence core",
        "exceptional_diversity": "Exceptional diversity concentration",
        "diversity_core": "Multi-year diversity core",
        "not_selected": "Not selected as High/Very high",
    }).astype("string")
    out["cell_justification"] = out.apply(justification, axis=1)
    out["conservation_priority_type"] = np.select(
        [
            convergence_class.eq("Muy alta"),
            convergence_class.eq("Alta") & out["evidence_family_low_occupancy_strong"] & out["evidence_family_richness_strong"],
            convergence_class.eq("Alta") & out["evidence_family_richness_strong"] & out["evidence_family_persistence_strong"],
            convergence_class.eq("Alta") & out["evidence_family_persistence_strong"] & out["evidence_family_repeated_use_strong"],
            convergence_class.eq("Alta"),
            out["ecological_priority_pathway_code"].eq("persistent_occurrence_and_diversity"),
            out["ecological_priority_pathway_code"].eq("persistent_occurrence") & out["strong_population_core_pathway"],
            out["ecological_priority_pathway_code"].eq("persistent_occurrence"),
            out["ecological_priority_pathway_code"].eq("exceptional_diversity"),
            out["ecological_priority_pathway_code"].eq("diversity_core") & out["strong_diversity_core_pathway"],
            out["ecological_priority_pathway_code"].eq("diversity_core"),
            out["evidence_family_low_occupancy_active"],
            out["evidence_family_richness_strong"],
        ],
        [
            "Very strong convergent biological evidence",
            "High diversity with repeated representation of low-occupancy species",
            "High richness and temporal persistence",
            "Temporal persistence and repeated use",
            "Convergent biological evidence",
            "Concurrent persistent occurrence and diversity evidence",
            "Strong persistent occurrence core",
            "Persistent occurrence core",
            "Exceptional diversity concentration",
            "Strong diversity core",
            "Multi-year diversity core",
            "Repeated representation of low-occupancy species",
            "High richness",
        ],
        default="Combined biological evidence",
    )
    out.drop(columns=["_convergence_priority_class"], inplace=True)

    high = out["ecological_priority_class"].isin(["Alta", "Muy alta"])
    out["validation_need"] = np.select(
        [
            high & out["exceptional_diversity_core_pathway"],
            high & out["data_adequacy_class"].isin([DATA_NOT_EVALUABLE, "Muy baja", "Baja"]),
            high & out["sensitivity_class"].eq("Sensible a ponderación ecológica"),
            high,
            out["monitoring_priority_class"].isin(["Alta", "Muy alta"]),
        ],
        [
            "Priority temporal validation: exceptional diversity concentration with still-limited temporal coverage",
            "Priority field validation because data adequacy is limited",
            "Compare ecological weighting scenarios with expert knowledge",
            "Routine validation before management decisions",
            "Reinforce temporal monitoring; this signal does not modify ecological priority",
        ], default="Complementary monitoring",
    )
    out["management_action_cell"] = np.select(
        [
            out["ecological_priority_class"].eq("Muy alta"),
            out["ecological_priority_class"].eq("Alta"),
            out["ecological_priority_class"].eq("Media"),
            out["ecological_priority_class"].eq("Sin capacidad de discriminación"),
            out["ecological_priority_class"].eq(ECO_NOT_EVALUABLE),
        ],
        [
            "Prioritise ecological validation and assessment of protection or connectivity",
            "Maintain monitoring and assess adapted management measures",
            "Retain as a complementary surveillance area",
            "Do not rank; increase information before prioritisation",
            "Do not assign an ecological class: no biological metrics are estimable; data adequacy is reported separately",
        ], default="No priority ecological action; retain as a reference",
    )

    diagnostics = {
        "priority_method": "multi_evidence_minimum_planning_unit",
        "convergence_high_min_events": 6,
        "convergence_high_min_abundance": 6,
        "convergence_very_high_min_events": 12,
        "convergence_very_high_min_abundance": 12,
        "ecological_discriminating": bool(ecological_discriminating),
        "richness_strong_threshold_species": 3,
        "richness_moderate_threshold_species": 2,
        "persistence_strong_threshold_years": 3,
        "persistence_moderate_threshold_years": 2,
        "repeated_use_strong_threshold_events": 10,
        "repeated_use_moderate_threshold_events": 4,
        "low_occupancy_species_fraction": 0.10,
        "population_core_moderate_min_years": 3,
        "population_core_moderate_min_events": 8,
        "population_core_moderate_min_abundance": 8,
        "population_core_strong_min_years": 4,
        "population_core_strong_min_events": 12,
        "population_core_strong_min_abundance": 12,
        "diversity_core_min_species": 4,
        "diversity_core_min_years": 2,
        "diversity_core_min_events": 5,
        "exceptional_diversity_min_species": 5,
        "exceptional_diversity_min_events": 12,
        "exceptional_diversity_min_low_occupancy_species": 2,
        "low_occupancy_threshold_cells": rare_diagnostics.get("low_occupancy_threshold_cells", np.nan),
        "n_low_occupancy_species": rare_diagnostics.get("n_low_occupancy_species", 0),
        "lcbd_context_informative": bool(lcbd_informative),
        "abundance_context_informative": bool(abundance_informative),
        "lcbd_q50": lcbd_q["q50"], "lcbd_q75": lcbd_q["q75"], "lcbd_q90": lcbd_q["q90"],
        "abundance_q50": abundance_q["q50"], "abundance_q75": abundance_q["q75"], "abundance_q90": abundance_q["q90"],
    }
    return gpd.GeoDataFrame(out, geometry="geometry", crs=priority.crs), diagnostics

def _load_protected(
    path: Path | None,
    target_crs: Any,
    study_geometry: Any | None = None,
    audit_rows: list[dict[str, Any]] | None = None,
) -> gpd.GeoDataFrame | None:
    if path is None or not path.exists():
        if audit_rows is not None:
            audit_rows.append({"source": str(path) if path is not None else "", "status": "not_evaluated", "detail": "protected-area path missing or not configured"})
        return None
    candidates = [path] if path.is_file() else sorted(path.rglob("*.shp")) + sorted(path.rglob("*.gpkg"))
    layers: list[gpd.GeoDataFrame] = []
    search_target = None
    clip_bounds = None
    if study_geometry is not None:
        search_target = gpd.GeoSeries([study_geometry], crs=target_crs)
        if not search_target.crs.is_geographic:
            search_target = search_target.buffer(100_000)
        clip_bounds = tuple(map(float, search_target.total_bounds))
    for candidate in candidates:
        try:
            bbox = None
            if search_target is not None:
                info = pyogrio.read_info(candidate)
                source_crs = info.get("crs")
                if source_crs:
                    search = search_target.to_crs(source_crs)
                    bbox = tuple(search.total_bounds)
            frame = gpd.read_file(candidate, bbox=bbox, engine="pyogrio")
            if frame.empty or frame.crs is None:
                if audit_rows is not None:
                    audit_rows.append({"source": str(candidate), "status": "omitted", "detail": "empty layer or missing CRS"})
                continue
            name_field = _first_field(
                frame.columns,
                (
                    "nombre", "name", "nom", "espacio", "site_name",
                    "sitename", "denominacion", "designation_name",
                ),
            )
            type_field = _first_field(
                frame.columns,
                (
                    "tipo", "type", "figura", "figura_lp", "categoria",
                    "designation", "desig", "desig_eng", "designatio",
                    "site_type", "sitetype",
                ),
            )
            level_field = _first_field(
                frame.columns,
                (
                    "nivel", "level", "nivel_proteccion", "protection_level",
                    "nivel_prot", "prot_level", "protection", "ambito", "scope",
                    "categoria_uicn", "iucn_cat", "iucn_category",
                    "designation_level", "designation_type", "desig_type",
                ),
            )
            selected_fields = list(dict.fromkeys(
                field for field in (name_field, type_field, level_field) if field
            ))
            frame = frame[[*selected_fields, "geometry"]].copy()
            rename: dict[str, str] = {}
            if name_field:
                rename[name_field] = "protected_name"
            if type_field:
                rename[type_field] = "protected_type"
            if level_field:
                rename[level_field] = "protected_level"
            frame = frame.rename(columns=rename)
            frame["protected_name"] = frame.get("protected_name", candidate.stem)
            frame["protected_type"] = frame.get("protected_type", "Protection designation")
            frame["protected_level"] = frame.get("protected_level", "Not specified")
            frame["protected_name"] = frame["protected_name"].map(_repair_mojibake)
            frame["protected_type"] = frame["protected_type"].map(_repair_mojibake)
            frame["protected_level"] = frame["protected_level"].map(_repair_mojibake)
            frame["protected_source"] = candidate.name
            frame = frame.to_crs(target_crs)
            # Trim source polygons to the same study + 100 km search extent
            # already used for source discovery. Geometry outside it cannot
            # affect overlap or nearest-area results within the defined scope.
            if clip_bounds is not None:
                xmin, ymin, xmax, ymax = clip_bounds
                def _clip_protected_geometry(geometry):
                    if geometry is None or geometry.is_empty:
                        return geometry
                    clipped = clip_by_rect(geometry, xmin, ymin, xmax, ymax)
                    return make_valid(clipped) if clipped is not None and not clipped.is_empty else clipped
                frame.geometry = frame.geometry.map(_clip_protected_geometry)
                frame = frame[(~frame.geometry.isna()) & (~frame.geometry.is_empty)].copy()
            if frame.empty:
                if audit_rows is not None:
                    audit_rows.append({"source": str(candidate), "status": "omitted", "detail": "no geometry inside protected-area search extent"})
                continue
            layers.append(frame)
            if audit_rows is not None:
                suffix = " and clipped to search extent" if clip_bounds is not None else ""
                audit_rows.append({"source": str(candidate), "status": "loaded", "detail": f"{len(frame)} features read{suffix}"})
        except Exception as exc:
            if audit_rows is not None:
                audit_rows.append({"source": str(candidate), "status": "error", "detail": f"{type(exc).__name__}: {exc}"})
            continue
    if not layers:
        return None
    combined = pd.concat(layers, ignore_index=True)
    return gpd.GeoDataFrame(combined, geometry="geometry", crs=target_crs)


def _prepare_protected_for_map(
    protected: gpd.GeoDataFrame | None,
    bounds: tuple[float, float, float, float],
    land: gpd.GeoDataFrame | None = None,
    marine_mask: gpd.GeoDataFrame | None = None,
    simplify_m: float = PROTECTED_MAP_SIMPLIFY_M,
) -> gpd.GeoDataFrame:
    """Clip and simplify marine protection for the interactive viewer.

    The extent clip excludes remote designations, the land subtraction prevents
    terrestrial protected surfaces from being displayed, and simplification
    reduces the browser workload without changing the analysis geometries.
    """

    empty = gpd.GeoDataFrame(
        columns=["protected_name", "protected_type", "protected_level", "protected_source", "geometry"],
        geometry="geometry",
        crs=4326,
    )
    if protected is None or protected.empty or protected.crs is None:
        return empty

    keep = [
        column
        for column in ("protected_name", "protected_type", "protected_level", "protected_source", "geometry")
        if column in protected.columns
    ]
    display = protected[keep].copy()
    if "protected_name" not in display:
        display["protected_name"] = "Protected area"
    if "protected_type" not in display:
        display["protected_type"] = "Protection designation"
    if "protected_level" not in display:
        display["protected_level"] = "Not specified"
    if "protected_source" not in display:
        display["protected_source"] = "Protected-area layer"
    display = display[
        (~display.geometry.isna()) & (~display.geometry.is_empty)
    ].copy()
    if display.empty:
        return empty

    projected_crs = display.crs if not display.crs.is_geographic else "EPSG:3035"
    display = display.to_crs(projected_crs)
    clip_geometry = gpd.GeoSeries([box(*bounds)], crs=4326).to_crs(
        projected_crs
    ).iloc[0]
    display = display[display.geometry.intersects(clip_geometry)].copy()
    if display.empty:
        return empty

    display.geometry = display.geometry.map(make_valid)
    display.geometry = display.geometry.intersection(clip_geometry)
    display = display[
        (~display.geometry.isna()) & (~display.geometry.is_empty)
    ].copy()
    display = _clip_geometries_to_marine(display, land, marine_mask)
    if display is None or display.empty:
        return empty
    if simplify_m > 0 and not display.empty:
        display.geometry = display.geometry.simplify(
            float(simplify_m), preserve_topology=True
        )
        display = display[
            (~display.geometry.isna()) & (~display.geometry.is_empty)
        ].copy()
    return display


def _zone_spatial_roles(
    priority: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Separate priority cores, supporting extensions and validation candidates.

    Las extensiones son siempre unidades de prioridad Media adyacentes por borde
    (rook) a un núcleo Alta/Muy alta y se evalúan en un único anillo. No pueden
    originar una zona ni reclutar otras extensiones. Las candidatas para
    validación permanecen fuera de las zonas prioritarias.
    """

    core = priority[priority["ecological_priority_class"].isin(["Alta", "Muy alta"])].copy()
    core["zone_role_code"] = "priority_core"
    core["zone_role"] = "Priority core"

    empty = priority.iloc[0:0].copy()
    empty["zone_role_code"] = pd.Series(dtype="string")
    empty["zone_role"] = pd.Series(dtype="string")
    if core.empty:
        return core, empty.copy(), empty.copy()

    medium = priority[priority["ecological_priority_class"].eq("Media")].copy()
    if medium.empty:
        return core, empty.copy(), empty.copy()

    score = pd.to_numeric(medium.get("ecological_priority_score"), errors="coerce")
    years = pd.to_numeric(medium.get("n_years_observed"), errors="coerce")
    events = pd.to_numeric(medium.get("n_sampling_events"), errors="coerce")
    families = pd.to_numeric(medium.get("n_independent_ecological_families_active"), errors="coerce")

    extension_eligible = score.ge(37.5) & years.ge(2) & events.ge(4) & families.ge(2)
    extension_indices: list[Any] = []
    core_index = core.sindex
    for index, geometry in medium.loc[extension_eligible].geometry.items():
        rook_adjacent = False
        for candidate in core_index.query(geometry, predicate="intersects"):
            core_geometry = core.geometry.iloc[int(candidate)]
            try:
                shared_boundary = geometry.boundary.intersection(core_geometry.boundary)
                rook_adjacent = (not shared_boundary.is_empty) and float(shared_boundary.length) > 1e-6
            except Exception:
                rook_adjacent = False
            if rook_adjacent:
                break
        if rook_adjacent:
            extension_indices.append(index)

    extensions = medium.loc[extension_indices].copy() if extension_indices else empty.copy()
    extensions["zone_role_code"] = "supporting_extension"
    extensions["zone_role"] = "Supporting extension"

    candidate_mask = (
        score.ge(50.0) & years.ge(2) & events.ge(4) & families.ge(2)
        & ~medium.index.isin(extension_indices)
    )
    candidates = medium.loc[candidate_mask].copy()
    candidates["zone_role_code"] = "validation_candidate"
    candidates["zone_role"] = "Validation candidate"

    return (
        gpd.GeoDataFrame(core, geometry="geometry", crs=priority.crs),
        gpd.GeoDataFrame(extensions, geometry="geometry", crs=priority.crs),
        gpd.GeoDataFrame(candidates, geometry="geometry", crs=priority.crs),
    )


def _connected_zones(
    selected: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame, gpd.GeoDataFrame]:
    """Group priority cores and supporting extensions by rook contiguity.

    Dos unidades que solo se tocan en un vértice no forman la misma zona.
    La geometría zonal puede incluir extensiones Media elegibles, pero clase,
    puntuación y vía causal se calculan exclusivamente con los núcleos
    Alta/Muy alta. Para compatibilidad, si ``zone_role_code`` no existe, todas
    las unidades recibidas se consideran núcleos prioritarios.
    """

    if selected.empty:
        empty = gpd.GeoDataFrame(columns=["zone_id", "geometry"], geometry="geometry", crs=selected.crs)
        return empty, pd.DataFrame(), selected.copy()

    cells = selected.copy()
    if "zone_role_code" not in cells.columns:
        cells["zone_role_code"] = "priority_core"
    if "zone_role" not in cells.columns:
        cells["zone_role"] = np.where(cells["zone_role_code"].eq("priority_core"), "Priority core", "Supporting extension")

    graph = nx.Graph()
    graph.add_nodes_from(cells.index)
    spatial_index = cells.sindex
    for index, geometry in cells.geometry.items():
        for candidate in spatial_index.query(geometry, predicate="intersects"):
            other = cells.index[int(candidate)]
            if other == index:
                continue
            other_geometry = cells.geometry.loc[other]
            try:
                shared_boundary = geometry.boundary.intersection(other_geometry.boundary)
                rook_adjacent = (not shared_boundary.is_empty) and float(shared_boundary.length) > 1e-6
            except Exception:
                rook_adjacent = False
            if rook_adjacent:
                graph.add_edge(index, other)

    zone_lookup: dict[Any, str] = {}
    for number, component in enumerate(sorted(nx.connected_components(graph), key=lambda x: (-len(x), min(map(str, x)))), 1):
        for index in component:
            zone_lookup[index] = f"ZP-{number:03d}"
    cells["zone_id"] = [zone_lookup[index] for index in cells.index]

    # Supporting extensions cannot constitute a priority zone on their own.
    valid_zone_ids = set(
        cells.loc[cells["zone_role_code"].eq("priority_core"), "zone_id"].dropna().astype(str)
    )
    cells = cells[cells["zone_id"].astype(str).isin(valid_zone_ids)].copy()
    zones = cells.dissolve(by="zone_id", as_index=False)

    summaries: list[dict[str, Any]] = []
    for zone_id, group in cells.groupby("zone_id", observed=True):
        core_group = group[group["zone_role_code"].eq("priority_core")].copy()
        if core_group.empty:
            continue
        extension_group = group[group["zone_role_code"].eq("supporting_extension")].copy()
        classes = core_group["ecological_priority_class"].astype(str)
        strongest = max(classes, key=lambda value: PRIORITY_ORDER.get(value, -1))

        group_area = pd.to_numeric(group.get("Area_mar_km2"), errors="coerce")
        group_fallback = pd.Series(group.geometry.area / 1_000_000, index=group.index, dtype=float)
        group_area = group_area.where(group_area.gt(0), group_fallback).fillna(group_fallback)
        core_area = group_area.loc[core_group.index]
        extension_area = group_area.loc[extension_group.index] if not extension_group.empty else pd.Series(dtype=float)
        total_area_cells = float(group_area.sum()) if len(group_area) else np.nan
        total_core_area = float(core_area.sum()) if len(core_area) else np.nan
        total_extension_area = float(extension_area.sum()) if len(extension_area) else 0.0
        area_very_high = float(core_area.loc[classes.eq("Muy alta")].sum()) if len(core_area) else 0.0
        area_high = float(core_area.loc[classes.eq("Alta")].sum()) if len(core_area) else 0.0
        pct_very_high = 100.0 * area_very_high / total_core_area if total_core_area > 0 else np.nan
        pct_high = 100.0 * area_high / total_core_area if total_core_area > 0 else np.nan
        pct_extension = 100.0 * total_extension_area / total_area_cells if total_area_cells > 0 else 0.0
        dominant = "Muy alta" if np.isfinite(pct_very_high) and pct_very_high > 50.0 else "Alta"

        pathway_codes = core_group.get("ecological_priority_pathway_code", pd.Series("not_selected", index=core_group.index)).fillna("not_selected").astype(str)
        pathway_counts = pathway_codes.value_counts()
        selected_path_counts = pathway_counts.drop(labels=["not_selected"], errors="ignore")
        if selected_path_counts.empty:
            main_pathway_code = "mixed"
        else:
            max_count = int(selected_path_counts.max())
            leaders = sorted(selected_path_counts[selected_path_counts.eq(max_count)].index.tolist())
            main_pathway_code = leaders[0] if len(leaders) == 1 else "mixed"
        pathway_labels = {
            "convergence": "Convergent biological evidence",
            "persistent_occurrence": "Persistent occurrence core",
            "diversity_core": "Multi-year diversity core",
            "exceptional_diversity": "Exceptional diversity concentration",
            "persistent_occurrence_and_diversity": "Concurrent persistent occurrence and diversity evidence",
            "mixed": "Combination of causal pathways",
        }
        pathway_count_summary = "; ".join(
            f"{pathway_labels.get(code, code)}: {int(count)}"
            for code, count in sorted(selected_path_counts.items())
        )
        summaries.append(
            {
                "zone_id": zone_id,
                "n_cells": len(group),
                "n_core_cells": len(core_group),
                "n_extension_cells": len(extension_group),
                "area_core_km2": total_core_area,
                "area_extension_km2": total_extension_area,
                "pct_zone_area_extension": pct_extension,
                "ecological_priority_class_zone": dominant,
                "ecological_priority_class_zone_max": strongest,
                "ecological_priority_score_mean": _safe_mean(core_group["ecological_priority_score"]),
                "ecological_priority_score_median": _safe_median(core_group["ecological_priority_score"]),
                "ecological_priority_score_max": pd.to_numeric(core_group["ecological_priority_score"], errors="coerce").max(),
                "monitoring_priority_score_mean": _safe_mean(core_group.get("monitoring_priority_score", pd.Series(np.nan, index=core_group.index))),
                "data_adequacy_score_mean": _safe_mean(core_group.get("data_adequacy_score", pd.Series(np.nan, index=core_group.index))),
                "n_cells_very_high": int(classes.eq("Muy alta").sum()),
                "n_cells_high": int(classes.eq("Alta").sum()),
                "area_very_high_km2": area_very_high,
                "area_high_km2": area_high,
                "pct_area_very_high": pct_very_high,
                "pct_area_high": pct_high,
                "zone_class_rule": "dominant marine area among priority cores; supporting extensions do not alter ecological class",
                "hotspot_cells_any_scale": int(group["is_hotspot_any_scale"].sum()),
                "hotspot_cells_multiscale": int(group["is_hotspot_multiscale"].sum()),
                "hotspot_cells_persistent_all_scales": int(group["is_hotspot_persistent_all_scales"].sum()),
                "LCBD_mean": _safe_mean(group["LCBD"]),
                "LCBD_max": pd.to_numeric(group["LCBD"], errors="coerce").max(),
                "richness_mean": _safe_mean(group["richness"]),
                "richness_max": pd.to_numeric(group["richness"], errors="coerce").max(),
                "abundance_sum": pd.to_numeric(group["abundance"], errors="coerce").sum(min_count=1),
                "abundance_mean": _safe_mean(group["abundance"]),
                "hotspot_persistence_max": pd.to_numeric(group.get("hotspot_persistence", pd.Series(0, index=group.index)), errors="coerce").max(),
                "hotspot_persistence_mean": _safe_mean(group.get("hotspot_persistence", pd.Series(0, index=group.index))),
                "main_priority_type": mode_or_na(core_group.get("conservation_priority_type", pd.Series("Not classified", index=core_group.index))),
                "main_priority_pathway_code": main_pathway_code,
                "main_priority_pathway": pathway_labels.get(main_pathway_code, main_pathway_code),
                "priority_pathway_counts": pathway_count_summary,
                "n_cells_pathway_convergence": int(pathway_counts.get("convergence", 0)),
                "n_cells_pathway_persistent_occurrence": int(pathway_counts.get("persistent_occurrence", 0)),
                "n_cells_pathway_diversity_core": int(pathway_counts.get("diversity_core", 0)),
                "n_cells_pathway_exceptional_diversity": int(pathway_counts.get("exceptional_diversity", 0)),
                "n_cells_pathway_concurrent_alternatives": int(pathway_counts.get("persistent_occurrence_and_diversity", 0)),
                "hotspot_priority_types": " | ".join(sorted(group.get("hotspot_type", pd.Series(dtype="string")).dropna().astype(str).unique())),
                "community_clusters": " | ".join(sorted(group.get("community_cluster", pd.Series(dtype="string")).dropna().astype(str).unique())),
                "depth_median_zone": _safe_median(group["depth_mediana_grid"]),
                "depth_mean_zone": _safe_mean(group.get("depth_media_grid", pd.Series(np.nan, index=group.index))),
                "n_depth_valid_zone": pd.to_numeric(group["n_depth_valid"], errors="coerce").sum(min_count=1),
                "habitat_dominant_zone": mode_or_na(group["habitat_dominante_grid"]),
                "temporal_signal_mean": _safe_mean(group.get("temporal_signal_raw", pd.Series(np.nan, index=group.index))),
                "n_temporal_records_zone": pd.to_numeric(group.get("n_temporal_records", pd.Series(0, index=group.index)), errors="coerce").sum(min_count=1),
                "data_adequacy_class_zone": mode_or_na(core_group.get("data_adequacy_class", pd.Series("Not calculated", index=core_group.index))),
                "n_independent_ecological_families_strong_max": pd.to_numeric(core_group.get("n_independent_ecological_families_strong", pd.Series(np.nan, index=core_group.index)), errors="coerce").max(),
                "n_independent_ecological_families_active_max": pd.to_numeric(core_group.get("n_independent_ecological_families_active", pd.Series(np.nan, index=core_group.index)), errors="coerce").max(),
                "n_cells_richness_strong": int(pd.Series(core_group.get("evidence_family_richness_strong", False), index=core_group.index).fillna(False).astype(bool).sum()),
                "n_cells_persistence_strong": int(pd.Series(core_group.get("evidence_family_persistence_strong", False), index=core_group.index).fillna(False).astype(bool).sum()),
                "n_cells_repeated_use_strong": int(pd.Series(core_group.get("evidence_family_repeated_use_strong", False), index=core_group.index).fillna(False).astype(bool).sum()),
                "n_cells_low_occupancy_representation": int(pd.Series(core_group.get("evidence_family_low_occupancy_active", False), index=core_group.index).fillna(False).astype(bool).sum()),
                "low_occupancy_species_repeated_zone": " | ".join(sorted({sp.strip() for value in core_group.get("low_occupancy_species_repeated", pd.Series(dtype="string")).dropna().astype(str) for sp in value.split("|") if sp.strip()})),
                "n_cells_population_core": int(pd.Series(core_group.get("population_core_pathway", False), index=core_group.index).fillna(False).astype(bool).sum()),
                "n_cells_strong_population_core": int(pd.Series(core_group.get("strong_population_core_pathway", False), index=core_group.index).fillna(False).astype(bool).sum()),
                "population_core_species_zone": " | ".join(sorted({sp.strip() for value in core_group.get("population_core_species", pd.Series(dtype="string")).dropna().astype(str) for sp in value.split("|") if sp.strip()})),
                "n_cells_diversity_core": int(pd.Series(core_group.get("diversity_core_pathway", False), index=core_group.index).fillna(False).astype(bool).sum()),
                "n_cells_strong_diversity_core": int(pd.Series(core_group.get("strong_diversity_core_pathway", False), index=core_group.index).fillna(False).astype(bool).sum()),
                "n_cells_exceptional_diversity_core": int(pd.Series(core_group.get("exceptional_diversity_core_pathway", False), index=core_group.index).fillna(False).astype(bool).sum()),
                "planning_grid_km": pd.to_numeric(group.get("planning_grid_km", group.get("scale_km", pd.Series(np.nan, index=group.index))), errors="coerce").max(),
                "n_cells_stable_3_scenarios": int(core_group["n_escenarios_prioridad_alta"].eq(3).sum()),
                "n_cells_stable_2plus_scenarios": int(core_group["n_escenarios_prioridad_alta"].ge(2).sum()),
                "sensitivity_class_zone": mode_or_na(core_group.get("sensitivity_class", pd.Series("Not calculated", index=core_group.index))),
                "validated_marine_area_cells_sum_km2": pd.to_numeric(group.get("Area_mar_km2", pd.Series(np.nan, index=group.index)), errors="coerce").sum(min_count=1),
                "marine_geometry_area_cells_sum_km2": pd.to_numeric(group.get("Area_geometria_marina_km2", group.geometry.area / 1_000_000), errors="coerce").sum(min_count=1),
                "grid_id_list": " | ".join(sorted(group["master_id"].astype(str))),
                "core_grid_id_list": " | ".join(sorted(core_group["master_id"].astype(str))),
                "extension_grid_id_list": " | ".join(sorted(extension_group["master_id"].astype(str))) if not extension_group.empty else "",
                "cell_justifications": " | ".join(sorted(core_group.get("cell_justification", pd.Series(dtype="string")).dropna().astype(str).unique())),
                "cell_management_actions": " | ".join(sorted(group.get("management_action_cell", pd.Series(dtype="string")).dropna().astype(str).unique())),
                "validation_needs": " | ".join(sorted(group.get("validation_need", pd.Series(dtype="string")).dropna().astype(str).unique())),
            }
        )
    summary = pd.DataFrame(summaries)
    zones = zones[["zone_id", "geometry"]].merge(summary, on="zone_id", how="left")
    zones["area_zone_km2"] = zones.geometry.area / 1e6
    summary = summary.merge(zones[["zone_id", "area_zone_km2"]], on="zone_id", how="left")
    summary["area_union_minus_cell_geometries_km2"] = summary["area_zone_km2"] - summary["marine_geometry_area_cells_sum_km2"]
    return (
        gpd.GeoDataFrame(zones, geometry="geometry", crs=selected.crs),
        summary,
        gpd.GeoDataFrame(cells, geometry="geometry", crs=selected.crs),
    )



def _operational_conservation_zones(
    strategic_zones: gpd.GeoDataFrame,
    strategic_summary: pd.DataFrame,
    multiscale: dict[str, Any],
) -> tuple[gpd.GeoDataFrame, pd.DataFrame, gpd.GeoDataFrame]:
    """Delineate operational footprints from observed evidence on the official 1-km grid.

    Strategic prioritisation is neither recalculated nor modified. Each operational
    zone is the union of official MITECO 1-km cells with records intersecting a
    strategic priority zone. Components use rook connectivity only between evidence
    cells: empty bridge cells are never added to connect separate nuclei.
    """

    empty_zones = gpd.GeoDataFrame(
        columns=["operational_zone_id", "parent_zone_id", "geometry"],
        geometry="geometry", crs=getattr(strategic_zones, "crs", None),
    )
    empty_cells = gpd.GeoDataFrame(
        columns=["operational_zone_id", "parent_zone_id", "fine_grid_id", "geometry"],
        geometry="geometry", crs=getattr(strategic_zones, "crs", None),
    )
    if strategic_zones is None or strategic_zones.empty:
        return empty_zones, pd.DataFrame(), empty_cells

    scale_results = multiscale.get("scale_results", {}) if isinstance(multiscale, dict) else {}
    fine_result = scale_results.get(1, {}) if isinstance(scale_results, dict) else {}
    fine = fine_result.get("grid_with_records", gpd.GeoDataFrame())
    if fine is None or fine.empty or "geometry" not in fine:
        return empty_zones, pd.DataFrame(), empty_cells

    fine = gpd.GeoDataFrame(fine.copy(), geometry="geometry", crs=fine.crs)
    if fine.crs != strategic_zones.crs:
        fine = fine.to_crs(strategic_zones.crs)
    zone_geom = strategic_zones[["zone_id", "geometry"]].copy()
    zone_geom["zone_id"] = zone_geom["zone_id"].astype(str)
    zone_index = zone_geom.sindex

    evidence_rows: list[dict[str, Any]] = []
    for _, row in fine.iterrows():
        geometry = row.geometry
        if geometry is None or geometry.is_empty:
            continue
        try:
            geometry = make_valid(geometry)
        except Exception:
            pass
        best_zone_id = None
        best_geometry = None
        best_area = 0.0
        for candidate in zone_index.query(geometry, predicate="intersects"):
            zrow = zone_geom.iloc[int(candidate)]
            try:
                intersection = geometry.intersection(zrow.geometry)
                area = float(intersection.area) if intersection is not None and not intersection.is_empty else 0.0
            except Exception:
                intersection = None
                area = 0.0
            if area > best_area:
                best_area = area
                best_zone_id = str(zrow.zone_id)
                best_geometry = intersection
        # Pure boundary contacts and numerical slivers are not evidence footprints.
        if best_zone_id is None or best_geometry is None or best_area <= 1.0:
            continue
        payload = row.drop(labels=["geometry"]).to_dict()
        payload["parent_zone_id"] = best_zone_id
        payload["fine_grid_id"] = str(payload.get("grid_id", payload.get("grid_id_scale", "")))
        payload["fine_grid_km"] = 1
        payload["geometry"] = make_valid(best_geometry)
        evidence_rows.append(payload)

    if not evidence_rows:
        return empty_zones, pd.DataFrame(), empty_cells

    evidence = gpd.GeoDataFrame(evidence_rows, geometry="geometry", crs=strategic_zones.crs)
    evidence = evidence[(~evidence.geometry.isna()) & (~evidence.geometry.is_empty)].copy()
    if evidence.empty:
        return empty_zones, pd.DataFrame(), empty_cells

    evidence["operational_zone_id"] = pd.NA
    for parent_zone_id, group in evidence.groupby("parent_zone_id", observed=True, sort=True):
        graph = nx.Graph()
        graph.add_nodes_from(group.index)
        spatial_index = group.sindex
        for index, geometry in group.geometry.items():
            for candidate in spatial_index.query(geometry, predicate="intersects"):
                other = group.index[int(candidate)]
                if other == index:
                    continue
                other_geometry = group.geometry.loc[other]
                try:
                    shared = geometry.boundary.intersection(other_geometry.boundary)
                    rook_adjacent = (not shared.is_empty) and float(shared.length) > 1e-6
                except Exception:
                    rook_adjacent = False
                if rook_adjacent:
                    graph.add_edge(index, other)
        components = sorted(
            nx.connected_components(graph),
            key=lambda component: (-len(component), min(str(group.loc[i, "fine_grid_id"]) for i in component)),
        )
        for number, component in enumerate(components, 1):
            op_id = f"{parent_zone_id}-O{number:02d}"
            evidence.loc[list(component), "operational_zone_id"] = op_id

    evidence["operational_zone_id"] = evidence["operational_zone_id"].astype("string")
    operational = evidence.dissolve(by="operational_zone_id", as_index=False)

    parent_area: dict[str, float] = {}
    if strategic_summary is not None and not strategic_summary.empty and "zone_id" in strategic_summary.columns:
        areas = pd.to_numeric(strategic_summary.get("area_zone_km2"), errors="coerce")
        parent_area = dict(zip(strategic_summary["zone_id"].astype(str), areas))
    if not parent_area:
        parent_area = dict(zip(zone_geom["zone_id"].astype(str), zone_geom.geometry.area / 1_000_000))

    summaries: list[dict[str, Any]] = []
    for op_id, group in evidence.groupby("operational_zone_id", observed=True, sort=True):
        parent = str(group["parent_zone_id"].iloc[0])
        op_geometry = operational.loc[operational["operational_zone_id"].astype(str).eq(str(op_id)), "geometry"].iloc[0]
        area = float(op_geometry.area / 1_000_000)
        raw_parent_area = parent_area.get(parent, np.nan)
        parea = float(raw_parent_area) if pd.notna(raw_parent_area) else np.nan
        summaries.append({
            "operational_zone_id": str(op_id),
            "parent_zone_id": parent,
            "fine_grid_km": 1,
            "n_evidence_cells_1km": int(len(group)),
            "area_operational_km2": area,
            "parent_zone_area_km2": parea,
            "pct_parent_zone_evidence_footprint": 100.0 * area / parea if np.isfinite(parea) and parea > 0 else np.nan,
            "n_records_sum": pd.to_numeric(group.get("n_records", pd.Series(0, index=group.index)), errors="coerce").sum(min_count=1),
            "n_sampling_events_cell_sum": pd.to_numeric(group.get("n_sampling_events", pd.Series(0, index=group.index)), errors="coerce").sum(min_count=1),
            "n_sampling_events_cell_max": pd.to_numeric(group.get("n_sampling_events", pd.Series(0, index=group.index)), errors="coerce").max(),
            "n_years_observed_max": pd.to_numeric(group.get("n_years_observed", pd.Series(0, index=group.index)), errors="coerce").max(),
            "richness_max_1km": pd.to_numeric(group.get("richness", pd.Series(np.nan, index=group.index)), errors="coerce").max(),
            "abundance_sum_1km": pd.to_numeric(group.get("abundance", pd.Series(np.nan, index=group.index)), errors="coerce").sum(min_count=1),
            "fine_grid_id_list": " | ".join(sorted(group["fine_grid_id"].astype(str))),
            "operational_geometry_rule": "Official MITECO 1-km cells with observations inside the strategic zone; no empty bridge cells are added.",
        })
    summary = pd.DataFrame(summaries)
    operational = operational[["operational_zone_id", "geometry"]].merge(summary, on="operational_zone_id", how="left")
    return (
        gpd.GeoDataFrame(operational, geometry="geometry", crs=strategic_zones.crs),
        summary,
        gpd.GeoDataFrame(evidence, geometry="geometry", crs=strategic_zones.crs),
    )

def _protection_gap(
    zones: gpd.GeoDataFrame,
    summary: pd.DataFrame,
    protected: gpd.GeoDataFrame | None,
) -> pd.DataFrame:
    result = summary.copy()
    if result.empty:
        return result
    if protected is None or protected.empty:
        result["n_protected_areas_overlap"] = pd.NA
        result["protected_area_names"] = "Sin capa de áreas protegidas"
        result["protected_area_types"] = "Sin capa de áreas protegidas"
        result["protected_area_levels"] = "Sin capa de áreas protegidas"
        result["protected_area_sources"] = "Sin capa de áreas protegidas"
        result["protected_area_km2"] = np.nan
        result["pct_zone_protected"] = np.nan
        result["distance_to_protected_m"] = np.nan
        result["protection_evaluation_status"] = "not_evaluated"
        result["conservation_gap_status"] = "Sin información de protección"
        result["conservation_gap_action"] = "Incorporar la carpeta de áreas protegidas para evaluar solape, proximidad y gap de conservación."
        return result
    protected = protected.to_crs(zones.crs)
    protected_index = protected.sindex
    rows: list[dict[str, Any]] = []
    for _, zone in zones.iterrows():
        candidate_positions = protected_index.query(zone.geometry, predicate="intersects")
        intersects = protected.iloc[np.asarray(candidate_positions, dtype=int)]
        if len(intersects):
            local_union = intersects.geometry.union_all()
            intersection = zone.geometry.intersection(local_union)
            area = intersection.area / 1e6 if not intersection.is_empty else 0.0
            distance = 0.0
        else:
            area = 0.0
            try:
                nearest = protected_index.nearest(zone.geometry, return_all=False)
                nearest_position = int(np.asarray(nearest)[1, 0])
                distance = float(zone.geometry.distance(protected.geometry.iloc[nearest_position]))
            except Exception:
                distance = float(protected.geometry.distance(zone.geometry).min())
        zone_area_km2 = float(
            zone.get("area_zone_km2", zone.geometry.area / 1_000_000)
        )
        percentage = min(
            100.0,
            100 * area / max(zone_area_km2, np.finfo(float).eps),
        )
        if percentage >= 95:
            status = "Alta prioridad ya ampliamente protegida"
            action = "Revisar si las medidas actuales cubren hábitats, presiones y seguimiento específico de signátidos."
        elif percentage >= 50:
            status = "Alta prioridad mayoritariamente protegida"
            action = "Evaluar el sector no cubierto y revisar conectividad con la figura de protección existente."
        elif percentage > 0:
            status = "Alta prioridad parcialmente protegida"
            action = "Analizar ampliación funcional, medidas de borde o coordinación con la figura protegida existente."
        elif distance <= 1000:
            status = "Alta prioridad próxima a protección existente"
            action = "Valorar conectividad, ampliación de límites o seguimiento coordinado con el área protegida próxima."
        else:
            status = "Alta prioridad no protegida"
            action = "Priorizar validación de campo, análisis de presiones y valoración de medidas de gestión o protección."
        rows.append(
            {
                "zone_id": zone["zone_id"],
                "protection_evaluation_status": "evaluated",
                "n_protected_areas_overlap": intersects["protected_name"].dropna().astype(str).nunique(),
                "protected_area_names": " | ".join(sorted(intersects["protected_name"].dropna().astype(str).unique())) if len(intersects) else "Sin solape",
                "protected_area_types": " | ".join(sorted(intersects["protected_type"].dropna().astype(str).unique())) if len(intersects) else "Sin solape",
                "protected_area_levels": " | ".join(sorted(intersects["protected_level"].dropna().astype(str).unique())) if len(intersects) else "Sin solape",
                "protected_area_sources": " | ".join(sorted(intersects["protected_source"].dropna().astype(str).unique())) if len(intersects) else "Sin solape",
                "protected_area_km2": area,
                "pct_zone_protected": percentage,
                "distance_to_protected_m": distance,
                "conservation_gap_status": status,
                "conservation_gap_action": action,
            }
        )
    return result.merge(pd.DataFrame(rows), on="zone_id", how="left")


def _merge_temporal_signal(
    priority: gpd.GeoDataFrame,
    temporal_signal: pd.DataFrame,
) -> gpd.GeoDataFrame:
    """Merge the current temporal signal through the audited synthetic key.

    The spatial basis uses the official MITECO geometry. The temporal formula remains
    untouched until its dedicated phase, so its synthetic selected-scale key
    is translated through ``synthetic_master_id`` when available.
    """

    result = priority.copy()
    signal = temporal_signal.copy()
    if "synthetic_master_id" in result.columns:
        signal = signal.rename(columns={"master_id": "synthetic_master_id"})
        key = "synthetic_master_id"
    else:
        key = "master_id"
    if key not in signal.columns:
        raise KeyError(f"Temporal signal lacks the required join key: {key}")
    result[key] = result[key].astype("string")
    signal[key] = signal[key].astype("string")
    signal = signal.drop_duplicates(key)
    merged = result.merge(signal, on=key, how="left")
    return gpd.GeoDataFrame(merged, geometry="geometry", crs=priority.crs)


def _conservation_spatial_quality_control(
    priority: gpd.GeoDataFrame,
    zones: gpd.GeoDataFrame,
    zone_summary: pd.DataFrame,
) -> pd.DataFrame:
    """Strict checks for the official marine conservation geometry and areas."""

    checks: list[dict[str, Any]] = []

    def add(name: str, condition: bool, detail: Any) -> None:
        checks.append(
            {
                "check": name,
                "status": "PASS" if bool(condition) else "FAIL",
                "detail": detail,
            }
        )

    source = priority.get(
        "conservation_grid_source", pd.Series("", index=priority.index)
    ).astype(str)
    add(
        "official_miteco_conservation_grid",
        bool(source.str.match(r"^official_miteco_(?:selected_grid_direct_multiscale|\d+km_minimum_planning_unit)$").all()),
        " | ".join(sorted(source.unique().tolist())),
    )
    add(
        "official_cell_identifiers_unique",
        bool(priority["master_id"].astype(str).is_unique),
        int(priority["master_id"].nunique()),
    )
    valid_priority = (
        (~priority.geometry.isna())
        & (~priority.geometry.is_empty)
        & priority.geometry.is_valid
        & priority.geometry.area.gt(0)
    )
    add(
        "priority_marine_geometries_valid",
        bool(valid_priority.all()),
        int(valid_priority.sum()),
    )
    geometry_area = priority.geometry.area / 1_000_000
    stored_geometry_area = pd.to_numeric(
        priority.get("Area_geometria_marina_km2"), errors="coerce"
    )
    add(
        "cell_marine_geometry_area_reproducible",
        bool(np.allclose(geometry_area, stored_geometry_area, rtol=1e-10, atol=1e-9)),
        float(np.nanmax(np.abs(geometry_area - stored_geometry_area)))
        if len(priority)
        else 0.0,
    )

    if zones.empty:
        add("zone_marine_geometry_area_reproducible", True, "no selected zones")
        add("protected_percentage_same_denominator", True, "no selected zones")
    else:
        zone_geometry_area = zones.geometry.area / 1_000_000
        zone_stored_area = pd.to_numeric(zones["area_zone_km2"], errors="coerce")
        add(
            "zone_marine_geometry_area_reproducible",
            bool(np.allclose(zone_geometry_area, zone_stored_area, rtol=1e-10, atol=1e-9)),
            float(np.nanmax(np.abs(zone_geometry_area - zone_stored_area))),
        )
        summary = zone_summary.set_index("zone_id")
        known = summary["pct_zone_protected"].notna()
        if known.any():
            expected = (
                100
                * pd.to_numeric(summary.loc[known, "protected_area_km2"], errors="coerce")
                / pd.to_numeric(summary.loc[known, "area_zone_km2"], errors="coerce")
            ).clip(upper=100)
            actual = pd.to_numeric(
                summary.loc[known, "pct_zone_protected"], errors="coerce"
            )
            protection_ok = np.allclose(actual, expected, rtol=1e-10, atol=1e-8)
            maximum_error = float(np.nanmax(np.abs(actual - expected)))
        else:
            protection_ok = True
            maximum_error = 0.0
        add(
            "protected_percentage_same_denominator",
            bool(protection_ok),
            maximum_error,
        )
        add(
            "protected_area_not_greater_than_zone",
            bool(
                (
                    pd.to_numeric(
                        summary.get("protected_area_km2"), errors="coerce"
                    ).fillna(0)
                    <= pd.to_numeric(
                        summary["area_zone_km2"], errors="coerce"
                    ).fillna(0)
                    + 1e-8
                ).all()
            ),
            int(len(summary)),
        )

    frame = pd.DataFrame(checks)
    failed = frame.loc[frame["status"].eq("FAIL"), "check"].tolist()
    if failed:
        raise AssertionError(
            "Conservation spatial checks failed: " + ", ".join(failed)
        )
    return frame


def _zone_miteco_context(zones: gpd.GeoDataFrame, demarcations_path: Path | None) -> pd.DataFrame:
    if zones.empty or demarcations_path is None or not demarcations_path.exists():
        return pd.DataFrame({"zone_id": zones.get("zone_id", pd.Series(dtype="string")), "Region_MITECO_dominante": "No calculado", "Region_MITECO_lista": "No calculado"})
    regions = load_demarcations(demarcations_path, target_crs=zones.crs.to_epsg() or 3035).to_crs(zones.crs)
    intersections = gpd.overlay(zones[["zone_id", "geometry"]], regions[["Region_MITECO", "geometry"]], how="intersection", keep_geom_type=False)
    if intersections.empty:
        return pd.DataFrame({"zone_id": zones["zone_id"], "Region_MITECO_dominante": "Sin solape MITECO detectado", "Region_MITECO_lista": "Sin solape MITECO detectado"})
    intersections["overlap_area"] = intersections.geometry.area
    rows = []
    for zone_id, group in intersections.groupby("zone_id", observed=True):
        area = group.groupby("Region_MITECO", observed=True)["overlap_area"].sum().sort_values(ascending=False)
        rows.append({"zone_id": zone_id, "Region_MITECO_dominante": str(area.index[0]), "Region_MITECO_lista": " | ".join(sorted(map(str, area.index)))})
    return pd.DataFrame(rows)




def _fill_zone_miteco_context_from_core_cells(
    summary: pd.DataFrame,
    zone_cells: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Fill missing zonal MITECO labels from the priority-core planning units.

    Spatial overlay remains the preferred zonal context.  Very small/coast-clipped
    marine polygons can, however, fail to intersect a demarcation polygon because of
    tiny boundary differences.  In that case the official MITECO label already carried
    by the constituent priority-core cells is the authoritative fallback.  Supporting
    extensions never redefine the dominant region.
    """

    result = summary.copy()
    required = {"zone_id", "Region_MITECO"}
    if result.empty or zone_cells.empty or not required.issubset(zone_cells.columns):
        return result

    cells = zone_cells.copy()
    if "zone_role_code" in cells.columns:
        core = cells.loc[cells["zone_role_code"].astype(str).eq("priority_core")].copy()
    else:
        core = cells.copy()
    if core.empty:
        return result

    region = core["Region_MITECO"].astype("string").str.strip()
    valid = region.notna() & ~region.str.lower().isin({"", "nan", "none", "<na>"})
    core = core.loc[valid].copy()
    if core.empty:
        return result
    core["Region_MITECO"] = region.loc[valid].astype(str)

    area = pd.to_numeric(core.get("Area_mar_km2", pd.Series(np.nan, index=core.index)), errors="coerce")
    fallback_area = pd.Series(core.geometry.area / 1_000_000, index=core.index, dtype=float)
    core["_miteco_weight"] = area.where(area.gt(0), fallback_area).fillna(fallback_area).clip(lower=0)

    rows: list[dict[str, Any]] = []
    for zone_id, group in core.groupby("zone_id", observed=True):
        weights = group.groupby("Region_MITECO", observed=True)["_miteco_weight"].sum()
        if weights.empty:
            continue
        ranked = sorted(
            ((str(name), float(value)) for name, value in weights.items()),
            key=lambda item: (-item[1], item[0]),
        )
        rows.append(
            {
                "zone_id": zone_id,
                "_Region_MITECO_dominante_fallback": ranked[0][0],
                "_Region_MITECO_lista_fallback": " | ".join(sorted(name for name, _ in ranked)),
            }
        )
    if not rows:
        return result

    fallback = pd.DataFrame(rows)
    result = result.merge(fallback, on="zone_id", how="left")
    placeholders = {
        "", "nan", "none", "<na>",
        "no calculado", "not calculated",
        "sin solape miteco detectado", "no miteco overlap detected",
    }
    for target, source in (
        ("Region_MITECO_dominante", "_Region_MITECO_dominante_fallback"),
        ("Region_MITECO_lista", "_Region_MITECO_lista_fallback"),
    ):
        if target not in result.columns:
            result[target] = pd.NA
        current = result[target].astype("string").str.strip()
        needs_fill = current.isna() | current.str.lower().isin(placeholders)
        result.loc[needs_fill, target] = result.loc[needs_fill, source]
        result = result.drop(columns=[source])
    return result

def _cells_with_species_summary_for_map(
    priority: gpd.GeoDataFrame,
    assigned: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Add species abundance and density to each conservation-cell popup.

    Density uses the cell's validated ``Area_mar_km2`` exactly: the actual
    MITECO marine area after GSHHS land has been removed. This display-only
    summary does not alter analytical results or prioritisation tables.
    """

    display = priority.copy()
    display["species_cell_summary"] = "[]"
    if display.empty or assigned.empty:
        return display
    required_cells = {"master_id", "Area_mar_km2"}
    required_obs = {"grid_id", "Species", "N_total"}
    if not required_cells.issubset(display.columns) or not required_obs.issubset(assigned.columns):
        return display

    cells = pd.DataFrame(
        display[["master_id", "Area_mar_km2"]].drop_duplicates("master_id")
    ).copy()
    cells["grid_id"] = cells["master_id"].astype(str)
    cells["Area_mar_km2"] = pd.to_numeric(cells["Area_mar_km2"], errors="coerce")

    # Select only the observation fields needed by this display summary.
    # ``assigned`` already carries Area_mar_km2 in normal pipeline runs;
    # retaining it here and merging the validated cell area again would make
    # pandas create Area_mar_km2_x / Area_mar_km2_y and remove the canonical
    # Area_mar_km2 name used by the aggregation below.  The popup must use the
    # area attached to the priority cell, so avoid that ambiguous duplicate at
    # source.
    observations = pd.DataFrame(
        assigned.drop(columns="geometry", errors="ignore")[["grid_id", "Species", "N_total"]]
    ).copy()
    observations["grid_id"] = observations["grid_id"].astype(str)
    observations["Species"] = observations["Species"].astype("string").str.strip()
    observations["N_for_sum"] = pd.to_numeric(observations["N_total"], errors="coerce").fillna(0.0)
    observations = observations[
        observations["Species"].notna() & observations["Species"].ne("")
    ].merge(cells[["grid_id", "Area_mar_km2"]], on="grid_id", how="inner", validate="many_to_one")
    if observations.empty:
        return display

    species = (
        observations.groupby(["grid_id", "Species"], observed=True)
        .agg(abundance=("N_for_sum", "sum"), Area_mar_km2=("Area_mar_km2", "first"))
        .reset_index()
    )
    species["density"] = np.where(
        pd.to_numeric(species["Area_mar_km2"], errors="coerce").gt(0),
        species["abundance"] / species["Area_mar_km2"],
        np.nan,
    )
    species = species.sort_values(
        ["grid_id", "abundance", "Species"],
        ascending=[True, False, True],
        kind="stable",
    )

    summaries: dict[str, str] = {}
    for grid_id, group in species.groupby("grid_id", observed=True):
        rows = [
            [
                str(row.Species),
                float(row.abundance) if pd.notna(row.abundance) else None,
                float(row.density) if pd.notna(row.density) else None,
            ]
            for row in group.itertuples(index=False)
        ]
        summaries[str(grid_id)] = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    display["species_cell_summary"] = display["master_id"].astype(str).map(summaries).fillna("[]")
    return gpd.GeoDataFrame(display, geometry="geometry", crs=priority.crs)


def _zones_with_species_summary_for_map(
    zones: gpd.GeoDataFrame,
    selected_cells: gpd.GeoDataFrame,
    assigned: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Añade al mapa un resumen por especie sin alterar tablas ni resultados analíticos."""

    display = zones.copy()
    display["species_zone_summary"] = "[]"
    if display.empty or selected_cells.empty or assigned.empty:
        return display
    required_cells = {"zone_id", "master_id"}
    required_obs = {"grid_id", "Species", "N_total"}
    if not required_cells.issubset(selected_cells.columns) or not required_obs.issubset(assigned.columns):
        return display

    cells = pd.DataFrame(selected_cells.drop(columns="geometry", errors="ignore")).copy()
    cells["zone_id"] = cells["zone_id"].astype(str)
    cells["grid_id"] = cells["master_id"].astype(str)
    cells["Area_mar_km2"] = pd.to_numeric(
        cells.get("Area_mar_km2", pd.Series(np.nan, index=cells.index)), errors="coerce"
    )
    zone_area = cells.groupby("zone_id", observed=True)["Area_mar_km2"].sum(min_count=1)
    if "area_zone_km2" in display.columns:
        fallback_area = pd.to_numeric(
            display.set_index(display["zone_id"].astype(str))["area_zone_km2"], errors="coerce"
        )
        zone_area = _coalesce_numeric(zone_area, fallback_area)

    observations = pd.DataFrame(assigned.drop(columns="geometry", errors="ignore")).copy()
    observations["grid_id"] = observations["grid_id"].astype(str)
    observations["Species"] = observations["Species"].astype("string").str.strip()
    observations["N_for_sum"] = pd.to_numeric(observations["N_total"], errors="coerce").fillna(0.0)
    observations = observations[
        observations["Species"].notna() & observations["Species"].ne("")
    ].merge(cells[["grid_id", "zone_id"]].drop_duplicates(), on="grid_id", how="inner")
    if observations.empty:
        return display

    species = (
        observations.groupby(["zone_id", "Species"], observed=True)["N_for_sum"]
        .sum()
        .rename("abundance")
        .reset_index()
    )
    species["zone_area_km2"] = species["zone_id"].map(zone_area)
    species["density"] = np.where(
        pd.to_numeric(species["zone_area_km2"], errors="coerce").gt(0),
        species["abundance"] / species["zone_area_km2"],
        np.nan,
    )
    species = species.sort_values(
        ["zone_id", "abundance", "Species"], ascending=[True, False, True], kind="stable"
    )

    summaries: dict[str, str] = {}
    for zone_id, group in species.groupby("zone_id", observed=True):
        rows = [
            [
                str(row.Species),
                float(row.abundance) if pd.notna(row.abundance) else None,
                float(row.density) if pd.notna(row.density) else None,
            ]
            for row in group.itertuples(index=False)
        ]
        summaries[str(zone_id)] = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    display["species_zone_summary"] = display["zone_id"].astype(str).map(summaries).fillna("[]")
    return gpd.GeoDataFrame(display, geometry="geometry", crs=zones.crs)

def _interactive_map(
    priority: gpd.GeoDataFrame,
    descriptive_priority: gpd.GeoDataFrame,
    zones: gpd.GeoDataFrame,
    operational_zones: gpd.GeoDataFrame,
    protected: gpd.GeoDataFrame | None,
    path: Path,
    cartographic_context: MapContext,
    html_context: dict[str, object],
    marine_mask: gpd.GeoDataFrame | None = None,
) -> Path:
    cell_fields = [
        "master_id",
        "grid_purpose",
        "zone_role_code",
        "zone_role",
        "zone_id",
        "scale_km",
        "n_records",
        "ecological_priority_class",
        "ecological_priority_score",
        "ecological_priority_pathway",
        "ecological_priority_pathway_code",
        "ecological_convergent_evidence_score",
        "ecological_population_core_score",
        "ecological_diversity_core_score",
        "population_core_pathway",
        "strong_population_core_pathway",
        "diversity_core_pathway",
        "strong_diversity_core_pathway",
        "exceptional_diversity_core_pathway",
        "n_population_core_species",
        "n_strong_population_core_species",
        "max_population_core_events",
        "max_population_core_years",
        "max_population_core_abundance",
        "population_core_species",
        "monitoring_priority_class",
        "monitoring_priority_score",
        "data_adequacy_class",
        "data_adequacy_score",
        "data_adequacy_n_components",
        "n_sampling_events",
        "n_years_observed",
        "n_scales_evaluable",
        "ecological_richness_family_score",
        "ecological_persistence_family_score",
        "ecological_repeated_use_family_score",
        "ecological_low_occupancy_representation_family_score",
        "n_low_occupancy_species_repeated",
        "low_occupancy_species_repeated",
        "ecological_lcbd_context_score",
        "planning_grid_km",
        "n_observers_support",
        "n_habitat_valid_support",
        "conservation_priority_type",
        "strong_ecological_criterion",
        "hotspot_persistence",
        "hotspot_type",
        "is_hotspot_any_scale",
        "is_hotspot_multiscale",
        "is_hotspot_persistent_all_scales",
        "hotspot_lcbd",
        "hotspot_cluster",
        "LCBD",
        "LCBD_p_value_finest",
        "LCBD_significant",
        "richness",
        "abundance",
        "depth_mediana_grid",
        "n_depth_valid",
        "habitat_dominante_grid",
        "temporal_signal_raw",
        "n_temporal_records",
        "sensitivity_class",
        "n_scenarios_high_priority",
        "ecological_priority_score_balanced",
        "ecological_priority_class_balanced",
        "ecological_priority_score_biodiversity_focus",
        "ecological_priority_class_biodiversity_focus",
        "ecological_priority_score_persistence_focus",
        "ecological_priority_class_persistence_focus",
        "cell_justification",
        "validation_need",
        "management_action_cell",
        "species_cell_summary",
    ]
    zone_fields = [
        "zone_id",
        "label_lat",
        "label_lon",
        "n_cells",
        "n_core_cells",
        "n_extension_cells",
        "area_core_km2",
        "area_extension_km2",
        "pct_zone_area_extension",
        "ecological_priority_class_zone",
        "ecological_priority_class_zone_max",
        "ecological_priority_score_mean",
        "ecological_priority_score_median",
        "ecological_priority_score_max",
        "monitoring_priority_score_mean",
        "data_adequacy_score_mean",
        "area_very_high_km2",
        "area_high_km2",
        "pct_area_very_high",
        "pct_area_high",
        "zone_class_rule",
        "n_cells_very_high",
        "n_cells_high",
        "hotspot_cells_any_scale",
        "hotspot_cells_multiscale",
        "hotspot_cells_persistent_all_scales",
        "LCBD_mean",
        "LCBD_max",
        "richness_mean",
        "richness_max",
        "abundance_sum",
        "abundance_mean",
        "hotspot_persistence_max",
        "hotspot_persistence_mean",
        "main_priority_type",
        "main_priority_pathway",
        "main_priority_pathway_code",
        "priority_pathway_counts",
        "n_cells_pathway_convergence",
        "n_cells_pathway_persistent_occurrence",
        "n_cells_pathway_diversity_core",
        "n_cells_pathway_exceptional_diversity",
        "n_cells_pathway_concurrent_alternatives",
        "Region_MITECO_dominante",
        "Region_MITECO_lista",
        "hotspot_priority_types",
        "community_clusters",
        "depth_median_zone",
        "depth_mean_zone",
        "n_depth_valid_zone",
        "habitat_dominant_zone",
        "temporal_signal_mean",
        "n_temporal_records_zone",
        "data_adequacy_class_zone",
        "n_independent_ecological_families_strong_max",
        "n_independent_ecological_families_active_max",
        "n_cells_richness_strong",
        "n_cells_persistence_strong",
        "n_cells_repeated_use_strong",
        "n_cells_low_occupancy_representation",
        "low_occupancy_species_repeated_zone",
        "n_cells_population_core",
        "n_cells_strong_population_core",
        "population_core_species_zone",
        "n_cells_diversity_core",
        "n_cells_strong_diversity_core",
        "n_cells_exceptional_diversity_core",
        "planning_grid_km",
        "n_cells_stable_3_scenarios",
        "n_cells_stable_2plus_scenarios",
        "sensitivity_class_zone",
        "grid_id_list",
        "core_grid_id_list",
        "extension_grid_id_list",
        "cell_justifications",
        "cell_management_actions",
        "validation_needs",
        "area_zone_km2",
        "protection_evaluation_status",
        "n_protected_areas_overlap",
        "protected_area_names",
        "protected_area_types",
        "protected_area_levels",
        "protected_area_sources",
        "protected_area_km2",
        "pct_zone_protected",
        "distance_to_protected_m",
        "conservation_gap_status",
        "conservation_gap_action",
        "zone_justification",
        "management_interpretation",
        "zone_validation_priority",
        "zone_management_action",
        "species_zone_summary",
    ]
    operational_zone_fields = [
        "operational_zone_id", "parent_zone_id", "fine_grid_km",
        "n_evidence_cells_1km", "area_operational_km2", "parent_zone_area_km2",
        "pct_parent_zone_evidence_footprint", "n_records_sum",
        "n_sampling_events_cell_sum", "n_sampling_events_cell_max",
        "n_years_observed_max", "richness_max_1km", "abundance_sum_1km",
        "fine_grid_id_list", "operational_geometry_rule",
    ]
    # Preserve official geometries for calculations and identifiers. For
    # display only, subtract GSHHS land without intersecting a selected-cell
    # union; this keeps the official cell position while removing its land part.
    priority_display = _clip_geometries_to_marine(
        priority, cartographic_context.land, marine_mask=None
    )
    descriptive_display = _clip_geometries_to_marine(
        descriptive_priority, cartographic_context.land, marine_mask=None
    ) if descriptive_priority is not None and not descriptive_priority.empty else gpd.GeoDataFrame()
    zones_display = _clip_geometries_to_marine(
        zones, cartographic_context.land, marine_mask=None
    )
    operational_display = _clip_geometries_to_marine(
        operational_zones, cartographic_context.land, marine_mask=None
    ) if operational_zones is not None and not operational_zones.empty else gpd.GeoDataFrame()
    if zones_display is not None and not zones_display.empty:
        label_points = gpd.GeoSeries(
            zones_display.geometry.representative_point(),
            crs=zones_display.crs,
        ).to_crs(4326)
        zones_display = zones_display.copy()
        zones_display["label_lon"] = label_points.x.to_numpy()
        zones_display["label_lat"] = label_points.y.to_numpy()
    protected_frame = _prepare_protected_for_map(
        protected, cartographic_context.bounds, cartographic_context.land, marine_mask
    )
    return render_conservation_map(
        destination=path,
        cells=feature_collection(priority_display, cell_fields),
        descriptive_cells=feature_collection(descriptive_display, cell_fields),
        zones=feature_collection(zones_display, zone_fields),
        operational_zones=feature_collection(operational_display, operational_zone_fields),
        protected=feature_collection(
            protected_frame,
            ["protected_name", "protected_type", "protected_level", "protected_source"],
        ),
        coastline=feature_collection(cartographic_context.coastline),
        bounds=cartographic_context.bounds,
        context=html_context,
        downloads=html_context.get("map_downloads", {}).get("priority", {}),
    )


def _report_value(value: Any, digits: int = 2) -> str:
    """Formats a displayed value without altering the source table."""

    if value is None or pd.isna(value):
        return "Not available"
    if isinstance(value, (bool, np.bool_)):
        return "Yes" if value else "No"
    if isinstance(value, (float, np.floating)):
        return f"{value:,.{digits}f}"
    return str(value)


def _add_key_value_table(document: Document, rows: list[tuple[str, Any]]) -> None:
    """Adds a vertical area record while preserving long text."""

    table = document.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for label, value in rows:
        cells = table.add_row().cells
        cells[0].text = label
        cells[0].paragraphs[0].runs[0].bold = True
        cells[1].text = _report_value(value)


def _word_report(
    priority: gpd.GeoDataFrame,
    zones_summary: pd.DataFrame,
    operational_summary: pd.DataFrame,
    map_png: Path,
    logo: Path | None,
    path: Path,
    context: dict[str, object],
) -> Path:
    """Creates the complete Block 21 report, with a summary and one record per area."""

    document = Document()
    section = document.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width
    section.top_margin = Cm(1.3)
    section.bottom_margin = Cm(1.3)
    section.left_margin = Cm(1.3)
    section.right_margin = Cm(1.3)
    if logo and logo.exists():
        document.add_picture(str(logo), width=Cm(20))

    selected_count = int(priority["ecological_priority_class"].isin(["Alta", "Muy alta"]).sum())
    extension_count = int(priority.get("zone_role_code", pd.Series("not_in_zone", index=priority.index)).eq("supporting_extension").sum())
    candidate_count = int(priority.get("zone_role_code", pd.Series("not_in_zone", index=priority.index)).eq("validation_candidate").sum())
    regions = " | ".join(sorted({str(value) for value in zones_summary.get("Region_MITECO_dominante", pd.Series(dtype="string")).dropna() if str(value).strip()})) or "Not calculated"
    total_area = pd.to_numeric(zones_summary.get("area_zone_km2", pd.Series(dtype=float)), errors="coerce").sum()
    protected = pd.to_numeric(zones_summary.get("n_protected_areas_overlap", pd.Series(dtype=float)), errors="coerce")
    operational_summary = operational_summary.copy() if isinstance(operational_summary, pd.DataFrame) else pd.DataFrame()
    operational_count = len(operational_summary)
    operational_area = pd.to_numeric(operational_summary.get("area_operational_km2", pd.Series(dtype=float)), errors="coerce").sum()
    operational_parent_count = operational_summary.get("parent_zone_id", pd.Series(dtype="string")).dropna().astype(str).nunique() if not operational_summary.empty else 0

    document.add_heading("Hispa-Syng v1.0 (Hippo-DEC Project) — Priority conservation areas", 0)
    document.add_paragraph(
        "Complete technical report generated exclusively from the filtered data of the current run. "
        "It integrates the map of selected areas, the executive summary, a comparative synopsis, and detailed records for each area."
    )
    document.add_heading("Run scope", level=1)
    _add_key_value_table(document, [
        ("Selected resolution", f"{context.get('grid_km', 'Not available')} km"),
        ("Run period", context.get("year_tag", "See the run parameters")),
        ("MITECO subdivision(s) represented", regions),
        ("Planning units evaluated", len(priority)),
        ("Priority cores (High/Very high)", selected_count),
        ("Medium supporting extensions", extension_count),
        ("Medium validation-candidate units", candidate_count),
        ("Strategic priority areas", len(zones_summary)),
        ("Operational conservation areas", operational_count),
    ])
    document.add_heading("Map of selected strategic priority areas", level=1)
    if map_png.exists():
        document.add_picture(str(map_png), width=Cm(21))
    document.add_paragraph(
        "The map distinguishes High/Very-high priority cores from Medium supporting extensions that complete an area spatially. "
        "Extensions are included only when they are edge-adjacent to a core and meet minimum recurrence requirements; they do not alter area ecological class and cannot create an area on their own. "
        "Strong but isolated Medium units remain outside priority areas and are exported separately as validation candidates."
    )
    document.add_paragraph(
        "This strategic delineation is not modified to create the operational product. After strategic areas have been selected, Hispa-Syng identifies official MITECO 1-km cells containing observations inside each strategic area and merges only evidence cells that share an edge. Empty cells are never added to bridge separated concentrations. One strategic area may therefore contain several operational conservation areas. These evidence footprints are intended to focus feasible field or management action; they are not complete population boundaries or habitat-suitability models."
    )

    document.add_page_break()
    document.add_heading("Executive summary", level=1)
    _add_key_value_table(document, [
        ("Number of strategic priority areas", len(zones_summary)),
        ("Number of operational conservation areas", operational_count),
        ("Strategic areas with operational footprint", operational_parent_count),
        ("Total operational-footprint area (km²)", operational_area),
        ("Number of High/Very-high cores", selected_count),
        ("Number of Medium supporting extensions", extension_count),
        ("Number of Medium validation candidates", candidate_count),
        ("Total marine area of priority areas (km²)", total_area),
        ("Mean ecological-priority index (0–100)", _safe_mean(zones_summary.get("ecological_priority_score_mean", pd.Series(dtype=float)))),
        ("Maximum ecological-priority index (0–100)", pd.to_numeric(zones_summary.get("ecological_priority_score_max", pd.Series(dtype=float)), errors="coerce").max()),
        ("Areas overlapping protected areas", int(protected.gt(0).sum())),
        ("Areas with no overlap detected", int(protected.eq(0).sum())),
        ("Areas with protection not evaluated", int(protected.isna().sum())),
    ])
    document.add_heading("Interpretation and technical basis", level=1)
    document.add_paragraph(
        "Conservation priority uses three complementary pathways: convergent biological evidence, persistent occurrence cores of a species, and diversity cores. "
        "A single isolated observation cannot generate High/Very-high priority by itself. The persistent-occurrence pathway requires the same species across multiple years and events; the diversity pathway requires at least four species with multi-year support, except for exceptional diversity concentrations that are provisionally accepted with priority temporal validation. "
        "Strategic priority areas originate from those High/Very-high cores and may include one direct ring of adjacent Medium units with sufficient support as supporting extensions. Extensions do not alter ecological class; strong but isolated Medium units are reported separately as validation candidates. LCBD and hotspots are retained as singularity context, while temporal monitoring and data adequacy are reported separately. The operational footprint is derived afterwards from observed 1-km cells and does not alter any score, class, or strategic area."
    )
    document.add_paragraph(
        "The identified areas are technical proposals to guide field validation, monitoring, pressure assessment, and spatial planning. "
        "They do not constitute a statutory designation and do not, by themselves, demonstrate that a protected designation covers syngnathid habitats, pressures, or specific needs."
    )

    document.add_heading("Synthetic table by strategic priority area", level=1)
    if zones_summary.empty:
        document.add_paragraph("No High or Very high priority areas were formed in this run.")
    else:
        columns = [
            ("zone_id", "Area"), ("Region_MITECO_dominante", "MITECO"),
            ("ecological_priority_class_zone", "Ecological priority"), ("zone_validation_priority", "Validation"),
            ("ecological_priority_score_mean", "Mean ecological index"), ("area_zone_km2", "Area (km²)"),
            ("pct_zone_protected", "% protected"), ("habitat_dominant_zone", "Habitat"),
            ("zone_management_action", "Recommended action"),
        ]
        table = document.add_table(rows=1, cols=len(columns))
        table.style = "Table Grid"
        for cell, (_, label) in zip(table.rows[0].cells, columns):
            cell.text = label
            cell.paragraphs[0].runs[0].bold = True
        for _, row in zones_summary.sort_values(["ecological_priority_score_mean", "zone_id"], ascending=[False, True]).iterrows():
            cells = table.add_row().cells
            for cell, (field, _) in zip(cells, columns):
                value = row.get(field, pd.NA)
                if field == "habitat_dominant_zone" and pd.notna(value):
                    value = translate_habitat_value(str(value))
                cell.text = _report_value(value, digits=1)

    document.add_heading("Operational conservation areas", level=1)
    document.add_paragraph(
        "Operational areas are 1-km evidence subareas contained within a strategic area. They retain the parent identifier and summarise the spatial footprint and observation support used to focus more manageable conservation action."
    )
    if operational_summary.empty:
        document.add_paragraph("No operational conservation areas were generated in this run.")
    else:
        operational_columns = [
            ("operational_zone_id", "Operational area"), ("parent_zone_id", "Strategic area"),
            ("n_evidence_cells_1km", "Evidence cells (1 km)"), ("area_operational_km2", "Operational area (km²)"),
            ("pct_parent_zone_evidence_footprint", "% of strategic area"), ("n_records_sum", "Records"),
            ("n_sampling_events_cell_sum", "Proxy events (sum)"), ("n_years_observed_max", "Maximum observed years"),
            ("richness_max_1km", "Maximum 1-km richness"), ("abundance_sum_1km", "1-km abundance"),
        ]
        table = document.add_table(rows=1, cols=len(operational_columns))
        table.style = "Table Grid"
        for cell, (_, label) in zip(table.rows[0].cells, operational_columns):
            cell.text = label
            cell.paragraphs[0].runs[0].bold = True
        for _, row in operational_summary.sort_values(["parent_zone_id", "operational_zone_id"], kind="stable").iterrows():
            cells = table.add_row().cells
            for cell, (field, _) in zip(cells, operational_columns):
                cell.text = _report_value(row.get(field, pd.NA), digits=2)

    document.add_page_break()
    document.add_heading("Complete technical records by strategic priority area", level=1)
    document.add_paragraph(
        "Each record presents the spatial, ecological, temporal, robustness, and conservation information available for the area. "
        "Cell identifiers, justifications, and validation needs make it possible to trace the evidence to the cells that form each area."
    )
    field_labels = [
        ("zone_id", "Priority area"), ("Region_MITECO_dominante", "Dominant MITECO subdivision"),
        ("Region_MITECO_lista", "Overlapping MITECO subdivisions"), ("ecological_priority_class_zone", "Ecological priority"),
        ("zone_validation_priority", "Validation priority"),
        ("data_adequacy_class_zone", "Data adequacy"), ("sensitivity_class_zone", "Stability across scenarios"),
        ("n_cells", "Total planning units"), ("n_core_cells", "Priority cores"),
        ("n_extension_cells", "Supporting extensions"), ("area_core_km2", "Core area (km²)"),
        ("area_extension_km2", "Extension area (km²)"), ("pct_zone_area_extension", "Area represented by extensions (%)"),
        ("area_zone_km2", "Total estimated marine area (km²)"),
        ("ecological_priority_score_mean", "Mean ecological index (0–100)"), ("ecological_priority_score_max", "Maximum ecological index (0–100)"),
        ("main_priority_pathway", "Dominant causal pathway"),
        ("priority_pathway_counts", "Causal pathway distribution"),
        ("main_priority_type", "Dominant priority type"),
        ("n_cells_population_core", "Cells with persistent occurrence core"),
        ("population_core_species_zone", "Species with persistent occurrence core"),
        ("n_cells_diversity_core", "Cells with diversity core"),
        ("n_cells_exceptional_diversity_core", "Cells with exceptional diversity concentration"),
        ("richness_max", "Maximum richness"),
        ("abundance_sum", "Total abundance"), ("LCBD_max", "Maximum LCBD"),
        ("hotspot_cells_any_scale", "Hotspot cells at any scale"), ("hotspot_cells_multiscale", "Multiscale hotspot cells"),
        ("hotspot_cells_persistent_all_scales", "Hotspot cells persistent at all scales"),
        ("pct_zone_protected", "Area protected (%)"), ("n_protected_areas_overlap", "Number of overlapping protected areas"),
        ("protected_area_names", "Protected-area names"), ("protected_area_types", "Protection designations"),
        ("protected_area_levels", "Protection levels"), ("distance_to_protected_m", "Distance to nearest protected area (m)"),
        ("habitat_dominant_zone", "Dominant habitat"), ("depth_median_zone", "Median area depth (m)"),
        ("monitoring_priority_score_mean", "Mean monitoring-priority index (0–100)"), ("community_clusters", "Community clusters"),
        ("zone_management_action", "Recommended action"), ("zone_justification", "Scientific justification"),
        ("management_interpretation", "Management interpretation"), ("validation_needs", "Validation needs"),
        ("cell_justifications", "Cell justifications"), ("cell_management_actions", "Cell-derived actions"),
        ("core_grid_id_list", "MITECO core identifiers"),
        ("extension_grid_id_list", "MITECO extension identifiers"),
        ("grid_id_list", "All MITECO identifiers in the area"),
    ]
    if zones_summary.empty:
        document.add_paragraph("No records are generated because no priority areas were selected in this run.")
    else:
        ordered_zones = zones_summary.sort_values(
            ["ecological_priority_score_mean", "zone_id"], ascending=[False, True]
        )
        for index, (_, row) in enumerate(ordered_zones.iterrows()):
            document.add_heading(f"Priority area {row.get('zone_id')}", level=2)
            rows: list[tuple[str, Any]] = []
            for field, label in field_labels:
                value = row.get(field, pd.NA)
                if field == "habitat_dominant_zone" and pd.notna(value):
                    value = translate_habitat_value(str(value))
                rows.append((label, value))
            _add_key_value_table(document, rows)
            if index < len(ordered_zones) - 1:
                document.add_page_break()

    document.add_page_break()
    document.add_heading("Complementary files and traceability", level=1)
    document.add_paragraph(
        "Complete reusable and filterable information is retained in the cell-priority, selected-cell, strategic-area, operational-area, 1-km operational-evidence, sensitivity, conservation-gap, and management tables; "
        "in the Block 21 Excel workbook; in the cell and area GeoPackages; in the interactive map; and in the web-publication data package."
    )
    document.add_heading("Responsible use", level=1)
    document.add_paragraph(
        "Before using an area for management decisions, review sampling effort, temporal coverage, spatial precision, habitat, depth, local pressures, and overlap with protected designations."
    )
    # Translate analytical values while preserving the bilingual source tables.
    for paragraph in document.paragraphs:
        for run in paragraph.runs:
            run.text = translate_text(run.text)
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.text = translate_text(run.text)
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)
    return path


def _prepare_conservation_marine_geometry(
    priority: gpd.GeoDataFrame,
    gshhg_path: Path | None,
    marine_regions: gpd.GeoDataFrame | None = None,
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    """Clip planning units to the exact GSHHS marine geometry used for area.

    Official MITECO grids retain the complete polygon for multiscale assignment,
    whereas ``Area_mar_km2`` represents only the marine surface obtained as
    MITECO minus GSHHS land. Conservation must use that same marine geometry for
    zone delineation, areas and protection assessment.
    """

    result = priority.copy()
    if gshhg_path is None:
        if "Area_geometria_marina_km2" not in result.columns:
            result["Area_geometria_marina_km2"] = result.geometry.area / 1_000_000
        return result, {"status": "not_reclipped_no_gshhs", "cells_clipped": 0}

    clipped, qa = clip_occupied_cells_with_land(
        result, Path(gshhg_path), True, marine_regions=marine_regions
    )
    if len(clipped) != len(result):
        missing = sorted(set(result["master_id"].astype(str)) - set(clipped["master_id"].astype(str)))
        raise AssertionError(
            "The conservation marine clip removed planning units with positive marine surface: "
            + ", ".join(missing[:10])
        )

    clipped = clipped.loc[result.index].copy()
    clipped["Area_geometria_marina_km2"] = clipped.geometry.area / 1_000_000
    stored_marine = pd.to_numeric(clipped.get("Area_mar_km2"), errors="coerce")
    geometry_marine = pd.to_numeric(clipped["Area_geometria_marina_km2"], errors="coerce")
    area_source = clipped.get("Area_mar_source", pd.Series("", index=clipped.index)).astype("string")
    gshhs_mask = area_source.eq("gshhs_clipped_geometry") | area_source.isin({"", "<NA>", "nan", "None"})
    fallback_mask = area_source.eq("miteco_demarcation_fallback_geometry")
    exact_matches = np.isclose(
        geometry_marine.to_numpy(dtype=float),
        stored_marine.to_numpy(dtype=float),
        rtol=1e-10,
        atol=1e-9,
        equal_nan=False,
    )
    valid_geometry = pd.Series(exact_matches, index=clipped.index)
    valid_geometry.loc[fallback_mask] = geometry_marine.loc[fallback_mask].gt(0)
    valid_geometry.loc[~(gshhs_mask | fallback_mask)] = False
    if not bool(valid_geometry.all()):
        differences = (geometry_marine - stored_marine).abs()
        bad = clipped.loc[~valid_geometry, "master_id"].astype(str).tolist()
        raise AssertionError(
            "The conservation marine geometry is not valid for Area_mar_km2. "
            f"Maximum difference: {float(differences.loc[~valid_geometry].max()):.12g} km². "
            "Affected units: " + ", ".join(bad[:10])
        )
    clipped["marine_geometry_method"] = "GSHHS_primary_with_MITECO_demarcation_fallback_for_conservation"
    clipped["marine_geometry_status"] = "validated_against_Area_mar_km2"
    return gpd.GeoDataFrame(clipped, geometry="geometry", crs=result.crs), qa


def _conservation_planning_inputs(
    multiscale: dict[str, Any],
    selected_grid_km: int,
    assigned: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, int]:
    """Select a minimum 5-km planning unit for conservation.

    The 1-km resolution remains available for descriptive maps but is not used
    directly to delineate conservation areas because the opportunistic dataset
    contains many cells with a single observation. For 1-km runs, block 21 uses
    the official 5-km MITECO grid as the minimum planning unit. Runs at 5 and
    10 km retain their own resolution.
    """

    selected_grid_km = int(selected_grid_km)
    planning_grid_km = 5 if selected_grid_km < 5 else selected_grid_km
    scale_results = multiscale.get("scale_results", {})
    result = scale_results.get(planning_grid_km, {}) if isinstance(scale_results, dict) else {}
    planning = result.get("grid", gpd.GeoDataFrame()) if isinstance(result, dict) else gpd.GeoDataFrame()
    planning_points = result.get("points", gpd.GeoDataFrame()) if isinstance(result, dict) else gpd.GeoDataFrame()

    if planning is None or planning.empty:
        fallback = multiscale["master_hotspots"].copy()
        fallback["planning_grid_km"] = selected_grid_km
        fallback["selected_grid_km"] = selected_grid_km
        return fallback, assigned.copy(), selected_grid_km

    priority = planning.copy()
    if "grid_id" not in priority.columns:
        raise KeyError("The conservation planning grid does not contain grid_id.")
    priority["grid_id"] = priority["grid_id"].astype(str)
    priority["master_id"] = priority["grid_id"]
    priority["planning_grid_km"] = planning_grid_km
    priority["selected_grid_km"] = selected_grid_km
    priority["conservation_grid_source"] = f"official_miteco_{planning_grid_km}km_minimum_planning_unit"

    # Normalise fields used by the conservation outputs.
    if "depth_median" in priority.columns and "depth_mediana_grid" not in priority.columns:
        priority = priority.rename(columns={"depth_median": "depth_mediana_grid"})
    if "habitat_dominant" in priority.columns and "habitat_dominante_grid" not in priority.columns:
        priority = priority.rename(columns={"habitat_dominant": "habitat_dominante_grid"})
    if "hotspot" in priority.columns and "hotspot_lcbd" not in priority.columns:
        priority["hotspot_lcbd"] = priority["hotspot"].fillna(False).astype(bool)
    if "hotspot_significant_fdr" in priority.columns and "hotspot_lcbd_fdr" not in priority.columns:
        priority["hotspot_lcbd_fdr"] = priority["hotspot_significant_fdr"].fillna(False).astype(bool)
    priority["is_hotspot_any_scale"] = priority.get("hotspot", pd.Series(False, index=priority.index)).fillna(False).astype(bool)
    priority["is_hotspot_multiscale"] = False
    priority["is_hotspot_persistent_all_scales"] = False
    priority["hotspot_persistence"] = 0.0
    priority["hotspot_persistence_mean"] = 0.0
    priority["n_scales_evaluable"] = 1
    priority["multiscale_support_evaluable"] = True
    priority["hotspot_type"] = np.where(priority["is_hotspot_any_scale"], "High LCBD in planning unit", "No LCBD hotspot")
    priority["hotspot_cluster"] = 0
    priority["hotspot_cluster_method"] = "Not used to delineate conservation areas"

    if planning_points is None or planning_points.empty:
        # Fallback espacial: reasigna los puntos de la ejecución a la unidad de planificación.
        local_points = assigned.to_crs(priority.crs).copy()
        polygons = priority[["master_id", "geometry"]].copy()
        joined = gpd.sjoin(local_points, polygons, how="inner", predicate="intersects")
        joined["grid_id"] = joined["master_id"].astype(str)
        planning_assigned = joined.drop(columns=["index_right"], errors="ignore")
    else:
        planning_assigned = planning_points.copy()
        if "grid_id_scale" in planning_assigned.columns:
            planning_assigned["grid_id"] = planning_assigned["grid_id_scale"].astype(str)
        elif "grid_id" in planning_assigned.columns:
            planning_assigned["grid_id"] = planning_assigned["grid_id"].astype(str)
        else:
            raise KeyError("The planning-scale assigned observations do not contain grid_id_scale/grid_id.")
        if not isinstance(planning_assigned, gpd.GeoDataFrame):
            planning_assigned = gpd.GeoDataFrame(planning_assigned, geometry="geometry", crs=assigned.crs)

    return gpd.GeoDataFrame(priority, geometry="geometry", crs=planning.crs), planning_assigned, planning_grid_km

def _descriptive_priority_inputs(
    multiscale: dict[str, Any],
    selected_grid_km: int,
    assigned: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Prepares descriptive priority at the resolution requested by the user.

    This layer is descriptive only. When a 1-km analysis is requested, it displays
    the ecological signal at 1 km while conservation areas continue to be delineated
    with 5-km minimum planning units.
    """

    selected_grid_km = int(selected_grid_km)
    scale_results = multiscale.get("scale_results", {})
    result = scale_results.get(selected_grid_km, {}) if isinstance(scale_results, dict) else {}
    if not isinstance(result, dict):
        return gpd.GeoDataFrame(), assigned.copy()

    descriptive = result.get("grid_all", gpd.GeoDataFrame())
    if descriptive is None or descriptive.empty:
        descriptive = result.get("grid_with_records", gpd.GeoDataFrame())
    if descriptive is None or descriptive.empty:
        descriptive = result.get("grid", gpd.GeoDataFrame())
    if descriptive is None or descriptive.empty:
        return gpd.GeoDataFrame(), assigned.copy()

    descriptive = descriptive.copy()
    if "grid_id" not in descriptive.columns and "grid_id_scale" in descriptive.columns:
        descriptive["grid_id"] = descriptive["grid_id_scale"].astype(str)
    if "grid_id" not in descriptive.columns:
        return gpd.GeoDataFrame(), assigned.copy()
    descriptive["grid_id"] = descriptive["grid_id"].astype(str)
    descriptive["master_id"] = descriptive["grid_id"]
    descriptive["planning_grid_km"] = selected_grid_km
    descriptive["selected_grid_km"] = selected_grid_km
    descriptive["conservation_grid_source"] = f"official_miteco_{selected_grid_km}km_descriptive_only"
    descriptive["grid_purpose"] = "descriptive"

    if "depth_median" in descriptive.columns and "depth_mediana_grid" not in descriptive.columns:
        descriptive = descriptive.rename(columns={"depth_median": "depth_mediana_grid"})
    if "habitat_dominant" in descriptive.columns and "habitat_dominante_grid" not in descriptive.columns:
        descriptive = descriptive.rename(columns={"habitat_dominant": "habitat_dominante_grid"})

    evaluated = result.get("grid", gpd.GeoDataFrame())
    if evaluated is not None and not evaluated.empty:
        evaluated = evaluated.copy()
        if "grid_id" not in evaluated.columns and "grid_id_scale" in evaluated.columns:
            evaluated["grid_id"] = evaluated["grid_id_scale"].astype(str)
        if "grid_id" in evaluated.columns:
            evaluated["grid_id"] = evaluated["grid_id"].astype(str)
            lookup = evaluated.drop_duplicates("grid_id").set_index("grid_id")
            for column in (
                "LCBD", "LCBD_p_value", "LCBD_p_adjust_BH", "LCBD_significant",
                "LCBD_significant_raw", "LCBD_significant_FDR", "hotspot",
                "hotspot_significant_fdr", "n_records", "n_sampling_events",
                "n_years_observed", "richness", "abundance",
            ):
                if column in lookup.columns:
                    mapped = descriptive["grid_id"].map(lookup[column])
                    if column not in descriptive.columns:
                        descriptive[column] = mapped
                    else:
                        descriptive[column] = descriptive[column].where(descriptive[column].notna(), mapped)

    if "hotspot" in descriptive.columns and "hotspot_lcbd" not in descriptive.columns:
        descriptive["hotspot_lcbd"] = descriptive["hotspot"].fillna(False).astype(bool)
    if "hotspot_significant_fdr" in descriptive.columns and "hotspot_lcbd_fdr" not in descriptive.columns:
        descriptive["hotspot_lcbd_fdr"] = descriptive["hotspot_significant_fdr"].fillna(False).astype(bool)
    descriptive["is_hotspot_any_scale"] = descriptive.get(
        "hotspot", pd.Series(False, index=descriptive.index)
    ).fillna(False).astype(bool)
    descriptive["is_hotspot_multiscale"] = False
    descriptive["is_hotspot_persistent_all_scales"] = False
    descriptive["hotspot_persistence"] = 0.0
    descriptive["hotspot_persistence_mean"] = 0.0
    descriptive["n_scales_evaluable"] = 1
    descriptive["multiscale_support_evaluable"] = True
    descriptive["hotspot_type"] = np.where(
        descriptive["is_hotspot_any_scale"],
        "High LCBD in descriptive cell",
        "No LCBD hotspot",
    )
    descriptive["hotspot_cluster"] = 0
    descriptive["hotspot_cluster_method"] = "Descriptive context; not used to delineate areas"

    descriptive_assigned = assigned.copy()
    if "grid_id" in descriptive_assigned.columns:
        descriptive_assigned["grid_id"] = descriptive_assigned["grid_id"].astype(str)
    return gpd.GeoDataFrame(descriptive, geometry="geometry", crs=descriptive.crs), descriptive_assigned


def run_conservation_analysis(
    multiscale: dict[str, Any],
    temporal: dict[str, Any],
    protected_path: Path | None,
    demarcations_path: Path | None,
    logo_path: Path | None,
    directories: dict[str, Path],
    registry: OutputRegistry,
    cartographic_context: MapContext,
    html_context: dict[str, object],
    selected_grid_km: int,
    assigned: gpd.GeoDataFrame,
    marine_mask: gpd.GeoDataFrame | None = None,
    gshhg_path: Path | None = None,
) -> dict[str, Any]:
    LOGGER.info("    [7/8 · 1/5] Integrating hotspots and temporal signal")
    root = directories["09_zonas_prioritarias_conservacion"]
    table_dir, figure_dir, map_dir, gis_dir, note_dir = (
        root / name for name in ("tables", "figures", "maps", "gis", "notes")
    )
    for directory in (table_dir, figure_dir, map_dir, gis_dir, note_dir):
        directory.mkdir(parents=True, exist_ok=True)

    priority, conservation_assigned, planning_grid_km = _conservation_planning_inputs(
        multiscale, selected_grid_km, assigned
    )
    priority["master_id"] = priority["master_id"].astype(str)
    priority["grid_purpose"] = "planning"
    conservation_regions = None
    if demarcations_path is not None and Path(demarcations_path).exists():
        conservation_regions = load_demarcations(
            Path(demarcations_path), target_crs=priority.crs.to_epsg() or 3035
        ).to_crs(priority.crs)
    priority, marine_geometry_qa = _prepare_conservation_marine_geometry(
        priority, gshhg_path, conservation_regions
    )
    LOGGER.info("    Descriptive priority resolution: %s km", selected_grid_km)
    LOGGER.info("    Conservation planning unit: %s km", planning_grid_km)
    if gshhg_path is not None:
        LOGGER.info(
            "    Conservation marine geometry validated with GSHHS: %d units; %d clipped by land.",
            len(priority), int(marine_geometry_qa.get("cells_clipped", 0)),
        )
    temporal_signal = temporal.get("temporal_signal_official", temporal.get("temporal_signal", pd.DataFrame())).copy()
    if "grid_id" in temporal_signal.columns and "master_id" not in temporal_signal.columns:
        temporal_signal = temporal_signal.rename(columns={"grid_id": "master_id"})
    if "master_id" not in temporal_signal.columns:
        temporal_signal = pd.DataFrame(columns=["master_id", "temporal_signal_raw", "n_temporal_records", "n_temporal_sampling_events"])
    priority = _merge_temporal_signal(priority, temporal_signal)
    rename = {"depth_median": "depth_mediana_grid", "habitat_dominant": "habitat_dominante_grid"}
    priority = priority.rename(columns={key: value for key, value in rename.items() if key in priority.columns and value not in priority.columns})
    defaults: dict[str, Any] = {
        "LCBD": np.nan, "richness": np.nan, "abundance": np.nan,
        "hotspot_lcbd": False, "hotspot_persistence": 0,
        "is_hotspot_any_scale": False, "is_hotspot_multiscale": False,
        "is_hotspot_persistent_all_scales": False, "depth_mediana_grid": np.nan,
        "n_depth_valid": np.nan, "habitat_dominante_grid": pd.NA,
        "temporal_signal_raw": np.nan, "n_temporal_records": np.nan,
    }
    for column, default in defaults.items():
        if column not in priority:
            priority[column] = default
    for column in ("LCBD", "richness", "abundance", "hotspot_persistence", "temporal_signal_raw", "n_temporal_records", "n_depth_valid"):
        priority[column] = pd.to_numeric(priority[column], errors="coerce")
    for column in ("is_hotspot_any_scale", "is_hotspot_multiscale", "is_hotspot_persistent_all_scales", "hotspot_lcbd"):
        priority[column] = priority[column].fillna(False).astype(bool)

    descriptive_priority = gpd.GeoDataFrame()
    descriptive_assigned = assigned.copy()
    if int(selected_grid_km) != int(planning_grid_km):
        descriptive_priority, descriptive_assigned = _descriptive_priority_inputs(
            multiscale, selected_grid_km, assigned
        )
        if descriptive_priority is not None and not descriptive_priority.empty:
            descriptive_priority, descriptive_marine_geometry_qa = _prepare_conservation_marine_geometry(
                descriptive_priority, gshhg_path, conservation_regions
            )
            descriptive_priority = _merge_temporal_signal(descriptive_priority, temporal_signal)
            for column, default in defaults.items():
                if column not in descriptive_priority:
                    descriptive_priority[column] = default
            for column in ("LCBD", "richness", "abundance", "hotspot_persistence", "temporal_signal_raw", "n_temporal_records", "n_depth_valid"):
                descriptive_priority[column] = pd.to_numeric(descriptive_priority[column], errors="coerce")
            for column in ("is_hotspot_any_scale", "is_hotspot_multiscale", "is_hotspot_persistent_all_scales", "hotspot_lcbd"):
                descriptive_priority[column] = descriptive_priority[column].fillna(False).astype(bool)
            descriptive_priority, descriptive_diagnostics = _build_priority_products(
                descriptive_priority, descriptive_assigned
            )
            descriptive_priority["zone_role_code"] = "descriptive_only"
            descriptive_priority["zone_role"] = "Descriptive only; not used to delineate areas"
            descriptive_priority["zone_id"] = pd.NA
            descriptive_priority["grid_purpose"] = "descriptive"
            descriptive_diagnostics["selected_grid_km"] = int(selected_grid_km)
            descriptive_diagnostics["planning_grid_km"] = int(planning_grid_km)

    LOGGER.info("    [7/8 · 2/5] Separate products: ecological priority, monitoring and data adequacy")
    priority, priority_diagnostics = _build_priority_products(priority, conservation_assigned)
    priority_diagnostics["selected_grid_km"] = int(selected_grid_km)
    priority_diagnostics["planning_grid_km"] = int(planning_grid_km)
    richness_p75 = float(pd.to_numeric(priority.get("richness"), errors="coerce").quantile(0.75)) if "richness" in priority.columns else np.nan

    LOGGER.info("    [7/8 · 3/5] Selección, extensiones de apoyo y agrupación de zonas prioritarias")
    expected_selected_count = int(priority["ecological_priority_class"].isin(["Alta", "Muy alta"]).sum())
    core_selected, zone_extensions, validation_candidates = _zone_spatial_roles(priority)
    zone_input = gpd.GeoDataFrame(
        pd.concat([core_selected, zone_extensions], axis=0),
        geometry="geometry", crs=priority.crs,
    )
    zones, zone_summary, zone_cells = _connected_zones(zone_input)
    operational_zones, operational_summary, operational_evidence_cells = _operational_conservation_zones(
        zones, zone_summary, multiscale
    )
    selected = zone_cells[zone_cells["zone_role_code"].eq("priority_core")].copy()
    zone_extensions = zone_cells[zone_cells["zone_role_code"].eq("supporting_extension")].copy()

    priority["zone_role_code"] = "not_in_zone"
    priority["zone_role"] = "Outside priority zone"
    priority["zone_id"] = pd.NA
    if not selected.empty:
        priority.loc[selected.index, "zone_role_code"] = "priority_core"
        priority.loc[selected.index, "zone_role"] = selected["zone_role"].astype(str)
        priority.loc[selected.index, "zone_id"] = selected["zone_id"].astype(str)
    if not zone_extensions.empty:
        priority.loc[zone_extensions.index, "zone_role_code"] = "supporting_extension"
        priority.loc[zone_extensions.index, "zone_role"] = zone_extensions["zone_role"].astype(str)
        priority.loc[zone_extensions.index, "zone_id"] = zone_extensions["zone_id"].astype(str)
    if not validation_candidates.empty:
        priority.loc[validation_candidates.index, "zone_role_code"] = "validation_candidate"
        priority.loc[validation_candidates.index, "zone_role"] = validation_candidates["zone_role"].astype(str)

    if len(selected) != expected_selected_count:
        raise AssertionError(
            f"Conservation output inconsistency: priority cores={len(selected)} but ecological High/Very-high cells={expected_selected_count}."
        )
    if not zone_extensions.empty and not zone_extensions["ecological_priority_class"].eq("Media").all():
        raise AssertionError("Supporting extensions must remain ecological-priority Medium units.")
    if not validation_candidates.empty and not validation_candidates["ecological_priority_class"].eq("Media").all():
        raise AssertionError("Validation candidates must remain ecological-priority Medium units.")
    overlap = set(selected.index) & set(zone_extensions.index) | set(selected.index) & set(validation_candidates.index) | set(zone_extensions.index) & set(validation_candidates.index)
    if overlap:
        raise AssertionError(f"Conservation spatial roles overlap for {len(overlap)} planning units.")
    if len(zones) != len(zone_summary):
        raise AssertionError(
            f"Conservation output inconsistency: zone geometries={len(zones)} but zone summaries={len(zone_summary)}."
        )
    if not selected.empty:
        assigned_zone_count = int(selected["zone_id"].nunique(dropna=True))
        if selected["zone_id"].isna().any() or assigned_zone_count != len(zone_summary):
            raise AssertionError(
                f"Conservation output inconsistency: priority-core zone assignments={assigned_zone_count}, zone summaries={len(zone_summary)}."
            )
    if not zone_summary.empty and pd.to_numeric(zone_summary.get("n_core_cells"), errors="coerce").fillna(0).le(0).any():
        raise AssertionError("Every priority zone must contain at least one High/Very-high priority core.")
    if not operational_zones.empty:
        parent_ids = set(zones["zone_id"].astype(str))
        if operational_zones["parent_zone_id"].isna().any() or not set(operational_zones["parent_zone_id"].astype(str)).issubset(parent_ids):
            raise AssertionError("Operational conservation zones must reference valid strategic parent zones.")
        zone_lookup_geom = zones.assign(_zone_key=zones["zone_id"].astype(str)).set_index("_zone_key").geometry
        outside_area = 0.0
        for _, op_row in operational_zones.iterrows():
            outside_area += float(op_row.geometry.difference(zone_lookup_geom.loc[str(op_row["parent_zone_id"])]).area)
        if outside_area > 1.0:
            raise AssertionError(f"Operational conservation geometry extends outside strategic zones by {outside_area:.3f} m².")
        if operational_evidence_cells.empty:
            raise AssertionError("Operational zones exist without 1-km evidence cells.")
    LOGGER.info("    [7/8 · 4/5] Protected-area coverage and gaps")
    protected_audit_rows: list[dict[str, Any]] = []
    protected = _load_protected(
        protected_path,
        priority.crs,
        priority.geometry.union_all(),
        audit_rows=protected_audit_rows,
    )
    protected_audit = pd.DataFrame(protected_audit_rows or [{"source": str(protected_path) if protected_path else "", "status": "not_evaluated", "detail": "no protected-area layer evaluated"}])
    protected_audit_path = csv2(protected_audit, directories["07_debug"] / "Auditoria_Capas_Areas_Protegidas.csv")
    registry.add(protected_audit_path, "QA", "Explicit protected-area layer audit")
    protected = _clip_geometries_to_marine(
        protected, cartographic_context.land, marine_mask
    )
    if protected is not None and protected.empty:
        protected = None
    zone_summary = _protection_gap(zones, zone_summary, protected)
    if not zone_summary.empty:
        zone_summary = zone_summary.merge(_zone_miteco_context(zones, demarcations_path), on="zone_id", how="left")
        zone_summary = _fill_zone_miteco_context_from_core_cells(zone_summary, zone_cells)
    if not zone_summary.empty:
        def _zone_justification(row: pd.Series) -> str:
            n_very_high = int(pd.to_numeric(row.get("n_cells_very_high", 0), errors="coerce") or 0)
            if n_very_high > 0:
                return (
                    f"Includes {n_very_high} Very high-priority planning unit(s), a class that can only be reached through strong convergence of biological evidence. "
                    "The area may also contain High units supported by other pathways, which are reported separately."
                )
            code = str(row.get("main_priority_pathway_code", "mixed"))
            counts = str(row.get("priority_pathway_counts", "")).strip()
            suffix = f" Pathway distribution: {counts}." if counts else ""
            if code == "convergence":
                return "The dominant causal pathway is convergence of at least three independent families of biological evidence." + suffix
            if code == "persistent_occurrence":
                return "The dominant causal pathway is a persistent occurrence core: the same species is repeatedly present across multiple years and independent events." + suffix
            if code == "diversity_core":
                return "The dominant causal pathway is a multi-year diversity core, with high richness supported across multiple years and independent events." + suffix
            if code == "exceptional_diversity":
                return "The dominant causal pathway is an exceptional diversity concentration with still-limited temporal coverage; priority temporal validation is required." + suffix
            if code == "persistent_occurrence_and_diversity":
                return "The dominant causal pathway combines persistent occurrence and a diversity core concurrently, without depending on isolated observations." + suffix
            return "The area combines several causal pathways of ecological priority; no isolated observation determines selection by itself." + suffix

        zone_summary["zone_justification"] = zone_summary.apply(_zone_justification, axis=1)
        zone_summary["management_interpretation"] = np.select(
            [zone_summary["ecological_priority_class_zone"].eq("Muy alta"), zone_summary["ecological_priority_class_zone"].eq("Alta")],
            ["Preferential attention and detailed validation", "Reinforced monitoring and territorial corroboration"],
            default="Complementary interest",
        )
        zone_summary["zone_management_action"] = np.select(
            [
                zone_summary.get("protection_evaluation_status", pd.Series("not_evaluated", index=zone_summary.index)).eq("not_evaluated"),
                zone_summary["ecological_priority_class_zone"].eq("Muy alta") & zone_summary["conservation_gap_status"].isin(["Alta prioridad no protegida", "Alta prioridad próxima a protección existente"]),
                zone_summary["ecological_priority_class_zone"].eq("Muy alta"),
                zone_summary["sensitivity_class_zone"].eq("Sensible a ponderación ecológica"),
                zone_summary["ecological_priority_class_zone"].isin(["Alta", "Muy alta"]),
            ],
            [
                "Validate in the field and assess protection coverage once a valid protected-area layer is available.",
                "Validate in the field, review pressures, and assess protection or connectivity.",
                "Ensure targeted monitoring and verify the adequacy of existing measures.",
                "Compare ecological weighting scenarios and expert knowledge before delineating measures.",
                "Maintain monitoring and assess adapted management measures.",
            ],
            default="Complementary monitoring.",
        )
        low_support = zone_summary["data_adequacy_class_zone"].isin([DATA_NOT_EVALUABLE, "Muy baja", "Baja"])
        zone_summary["zone_validation_priority"] = np.select(
            [
                zone_summary["ecological_priority_class_zone"].eq("Muy alta") & low_support,
                zone_summary["ecological_priority_class_zone"].eq("Muy alta"),
                zone_summary["ecological_priority_class_zone"].eq("Alta") & low_support,
                zone_summary["ecological_priority_class_zone"].eq("Alta"),
            ],
            ["Muy alta", "Alta", "Alta", "Media"],
            default="Baja",
        )
    if not zones.empty:
        zones = zones.drop(columns=[column for column in zone_summary.columns if column != "zone_id" and column in zones.columns], errors="ignore").merge(zone_summary, on="zone_id", how="left")
        zones = gpd.GeoDataFrame(zones, geometry="geometry", crs=priority.crs)

    spatial_qa = _conservation_spatial_quality_control(
        priority, zones, zone_summary
    )
    count_qa = pd.DataFrame([
        {
            "check": "selected_cell_count_consistent",
            "status": "PASS" if len(selected) == expected_selected_count else "FAIL",
            "detail": f"selected={len(selected)}; ecological_high_or_very_high={expected_selected_count}",
        },
        {
            "check": "priority_zone_count_consistent",
            "status": "PASS" if len(zones) == len(zone_summary) and (selected.empty or selected["zone_id"].nunique(dropna=True) == len(zone_summary)) else "FAIL",
            "detail": f"zone_geometries={len(zones)}; zone_summaries={len(zone_summary)}; selected_cell_zone_ids={selected['zone_id'].nunique(dropna=True) if not selected.empty else 0}",
        },
        {
            "check": "spatial_role_counts_consistent",
            "status": "PASS" if (
                int(priority["zone_role_code"].eq("priority_core").sum()) == len(selected)
                and int(priority["zone_role_code"].eq("supporting_extension").sum()) == len(zone_extensions)
                and int(priority["zone_role_code"].eq("validation_candidate").sum()) == len(validation_candidates)
            ) else "FAIL",
            "detail": (
                f"cores={len(selected)}; extensions={len(zone_extensions)}; candidates={len(validation_candidates)}; "
                f"priority_role_counts={priority['zone_role_code'].value_counts(dropna=False).to_dict()}"
            ),
        },
        {
            "check": "supporting_extensions_remain_medium",
            "status": "PASS" if zone_extensions.empty or zone_extensions["ecological_priority_class"].eq("Media").all() else "FAIL",
            "detail": f"extensions={len(zone_extensions)}; non_medium={int((~zone_extensions['ecological_priority_class'].eq('Media')).sum()) if not zone_extensions.empty else 0}",
        },
        {
            "check": "validation_candidates_remain_medium_and_outside_zones",
            "status": "PASS" if validation_candidates.empty or (
                validation_candidates["ecological_priority_class"].eq("Media").all()
                and validation_candidates.get("zone_id", pd.Series(pd.NA, index=validation_candidates.index)).isna().all()
            ) else "FAIL",
            "detail": f"candidates={len(validation_candidates)}",
        },
        {
            "check": "every_priority_zone_contains_core",
            "status": "PASS" if zone_summary.empty or pd.to_numeric(zone_summary.get("n_core_cells"), errors="coerce").fillna(0).gt(0).all() else "FAIL",
            "detail": f"zones={len(zone_summary)}; zones_without_core={int(pd.to_numeric(zone_summary.get('n_core_cells'), errors='coerce').fillna(0).le(0).sum()) if not zone_summary.empty else 0}",
        },
    ])
    spatial_qa = pd.concat([spatial_qa, count_qa], ignore_index=True)
    spatial_qa_path = csv2(
        spatial_qa,
        directories["07_debug"]
        / "Quality_Control_Conservation_Geometry.csv",
    )
    registry.add(
        spatial_qa_path,
        "QA",
        "Conservation geometry, area, and protection checks",
    )

    priority_diagnostics_table = pd.DataFrame([{**priority_diagnostics,
        "n_cells": int(len(priority)),
        "n_ecological_not_evaluable": int(priority["ecological_priority_class"].eq(ECO_NOT_EVALUABLE).sum()),
        "n_ecological_no_discrimination": int(priority["ecological_priority_class"].eq("Sin capacidad de discriminación").sum()),
        "n_ecological_high_or_very_high": int(priority["ecological_priority_class"].isin(["Alta", "Muy alta"]).sum()),
    }])
    priority_diagnostics_path = csv2(priority_diagnostics_table, directories["07_debug"] / "Diagnostico_Prioridad_Conservacion.csv")
    registry.add(priority_diagnostics_path, "QA", "Diagnóstico de prioridad ecológica, seguimiento y suficiencia de datos")

    non_public_diagnostic_columns = [
        "strong_ecological_criterion",
        "evidence_richness_p75", "evidence_temporal_high",
    ]
    priority_public = priority.drop(columns=non_public_diagnostic_columns, errors="ignore")
    descriptive_public = (
        descriptive_priority.drop(columns=non_public_diagnostic_columns, errors="ignore")
        if descriptive_priority is not None and not descriptive_priority.empty
        else gpd.GeoDataFrame()
    )
    selected_public = selected.drop(columns=non_public_diagnostic_columns, errors="ignore")
    extensions_public = zone_extensions.drop(columns=non_public_diagnostic_columns, errors="ignore")
    candidates_public = validation_candidates.drop(columns=non_public_diagnostic_columns, errors="ignore")
    zone_summary_public = zone_summary.copy()
    operational_summary_public = operational_summary.copy()
    operational_evidence_public = operational_evidence_cells.copy()

    priority_table = pd.DataFrame(priority_public.drop(columns="geometry")).sort_values("ecological_priority_score", ascending=False)
    descriptive_table = (
        pd.DataFrame(descriptive_public.drop(columns="geometry")).sort_values("ecological_priority_score", ascending=False)
        if descriptive_public is not None and not descriptive_public.empty
        else pd.DataFrame()
    )
    selected_table = pd.DataFrame(selected_public.drop(columns="geometry")).sort_values(["ecological_priority_class", "ecological_priority_score"], ascending=[False, False])
    extensions_table = pd.DataFrame(extensions_public.drop(columns="geometry")).sort_values("ecological_priority_score", ascending=False)
    candidates_table = pd.DataFrame(candidates_public.drop(columns="geometry")).sort_values("ecological_priority_score", ascending=False)
    sensitivity_columns = [
        "master_id", "ecological_priority_class", "ecological_priority_score",
        "ecological_priority_pathway", "ecological_priority_pathway_code",
        "ecological_convergent_evidence_score", "ecological_population_core_score", "ecological_diversity_core_score",
        "population_core_pathway", "strong_population_core_pathway",
        "diversity_core_pathway", "strong_diversity_core_pathway", "exceptional_diversity_core_pathway",
        "n_population_core_species", "population_core_species",
        "monitoring_priority_class", "monitoring_priority_score",
        "data_adequacy_class", "data_adequacy_score", "data_adequacy_n_components",
        "ecological_priority_class_balanced", "ecological_priority_score_balanced",
        "ecological_priority_class_biodiversity_focus", "ecological_priority_score_biodiversity_focus",
        "ecological_priority_class_persistence_focus", "ecological_priority_score_persistence_focus",
        "n_independent_ecological_families_active", "n_independent_ecological_families_strong",
        "n_escenarios_prioridad_alta", "sensitivity_class", "validation_need",
        "management_action_cell",
    ]
    sensitivity_table = priority_table[[column for column in sensitivity_columns if column in priority_table]].copy()
    gap_columns = [
        "zone_id", "ecological_priority_class_zone", "ecological_priority_class_zone_max", "ecological_priority_score_mean", "ecological_priority_score_median", "ecological_priority_score_max",
        "area_zone_km2", "area_very_high_km2", "area_high_km2", "pct_area_very_high", "pct_area_high",
        "protection_evaluation_status", "n_protected_areas_overlap", "protected_area_names",
        "protected_area_types", "protected_area_levels", "protected_area_sources", "protected_area_km2",
        "pct_zone_protected", "distance_to_protected_m", "conservation_gap_status",
        "conservation_gap_action", "zone_validation_priority", "zone_management_action",
    ]
    gap_table = zone_summary[[column for column in gap_columns if column in zone_summary]].copy()
    priority_table_export = translate_frame(priority_table)
    descriptive_table_export = translate_frame(descriptive_table) if not descriptive_table.empty else pd.DataFrame()
    selected_table_export = translate_frame(selected_table)
    extensions_table_export = translate_frame(extensions_table)
    candidates_table_export = translate_frame(candidates_table)
    zone_summary_export = translate_frame(zone_summary_public)
    operational_summary_export = translate_frame(operational_summary_public)
    operational_evidence_export = translate_frame(pd.DataFrame(operational_evidence_public.drop(columns="geometry", errors="ignore")))
    sensitivity_table_export = translate_frame(sensitivity_table)
    gap_table_export = translate_frame(gap_table)
    table_paths = [
        csv2(priority_table_export, table_dir / "Table_21_All_Conservation_Priority_Cells.csv"),
        csv2(selected_table_export, table_dir / "Table_21_Selected_Priority_Area_Cells.csv"),
        csv2(extensions_table_export, table_dir / "Table_21_Supporting_Area_Extensions.csv"),
        csv2(candidates_table_export, table_dir / "Table_21_Validation_Candidate_Units.csv"),
        csv2(zone_summary_export, table_dir / "Table_21_Priority_Conservation_Areas.csv"),
        csv2(operational_summary_export, table_dir / "Table_21_Operational_Conservation_Areas.csv"),
        csv2(operational_evidence_export, table_dir / "Table_21_1km_Operational_Evidence_Cells.csv"),
    ]
    if not descriptive_table_export.empty:
        descriptive_path = csv2(
            descriptive_table_export,
            table_dir / f"Table_21_Descriptive_Priority_{int(selected_grid_km)}km.csv",
        )
        registry.add(
            descriptive_path, "21",
            f"Descriptive priority at {int(selected_grid_km)} km; not used to delineate areas",
        )

    for path, description in zip(table_paths, [
        "Priority of all planning units", "High/Very-high priority cores",
        "Medium supporting area extensions", "Medium validation-candidate units",
        "Priority-area summary",
        "Operational conservation-area summary",
        "Official 1-km evidence cells delineating operational areas"
    ]):
        registry.add(path, "21", description)
    sensitivity_path = csv2(sensitivity_table_export, table_dir / "Table_21_Cell_Sensitivity_and_Robustness.csv")
    gap_path = csv2(gap_table_export, table_dir / "Table_21_Conservation_Gaps_and_Area_Management.csv")
    registry.add(sensitivity_path, "21", "Sensitivity and robustness by cell")
    registry.add(gap_path, "21", "Conservation gaps and management actions by area")
    book_sheets = {
        "planning_cells": priority_table_export,
        "priority_cores": selected_table_export,
        "area_extensions": extensions_table_export,
        "validation_candidates": candidates_table_export,
        "priority_areas": zone_summary_export,
        "operational_areas": operational_summary_export,
        "operational_evidence_1km": operational_evidence_export,
        "cell_sensitivity": sensitivity_table_export,
        "area_gaps_management": gap_table_export,
    }
    if not descriptive_table_export.empty:
        book_sheets["descriptive_priority"] = descriptive_table_export
    book = excel_book(
        book_sheets,
        table_dir / "Table_21_Priority_Conservation_Areas.xlsx",
    )
    registry.add(book, "21", "Detailed prioritisation and areas workbook")
    executive = pd.DataFrame(
        [
            {
                "n_zones": len(zone_summary),
                "n_operational_zones": len(operational_summary),
                "n_operational_evidence_cells_1km": len(operational_evidence_cells),
                "operational_area_total_km2": pd.to_numeric(operational_summary.get("area_operational_km2", pd.Series(dtype=float)), errors="coerce").sum(min_count=1) if len(operational_summary) else 0,
                "n_priority_core_cells": len(selected),
                "n_supporting_extension_cells": len(zone_extensions),
                "n_validation_candidate_cells": len(validation_candidates),
                "n_zone_cells_total": len(zone_cells),
                "n_cells_selected": len(selected),
                "n_zones_with_overlap": int(pd.to_numeric(zone_summary.get("n_protected_areas_overlap"), errors="coerce").gt(0).sum()) if len(zone_summary) else 0,
                "n_zones_without_overlap": int(pd.to_numeric(zone_summary.get("n_protected_areas_overlap"), errors="coerce").eq(0).sum()) if len(zone_summary) else 0,
                "n_zones_protection_not_evaluated": int(pd.to_numeric(zone_summary.get("n_protected_areas_overlap"), errors="coerce").isna().sum()) if len(zone_summary) else 0,
                "ecological_priority_score_mean": _safe_mean(zone_summary["ecological_priority_score_mean"]) if len(zone_summary) else np.nan,
                "ecological_priority_score_max": zone_summary["ecological_priority_score_max"].max() if len(zone_summary) else np.nan,
                "area_total_km2": zone_summary["area_zone_km2"].sum() if len(zone_summary) else 0,
            }
        ]
    )
    executive_path = csv2(executive, table_dir / "Summary_21_Priority_Conservation_Areas.csv")
    registry.add(executive_path, "21", "Executive conservation summary")

    grid_gpkg = gis_dir / "Conservation_Priority_Cells.gpkg"
    translate_geodataframe(priority_public).to_file(grid_gpkg, layer="planning_units", driver="GPKG", engine="pyogrio")
    if descriptive_public is not None and not descriptive_public.empty:
        translate_geodataframe(descriptive_public).to_file(
            grid_gpkg, layer="descriptive_priority", driver="GPKG", engine="pyogrio", append=True
        )
    registry.add(grid_gpkg, "21", "GeoPackage of descriptive priority and planning units")
    zones_gpkg = gis_dir / "Priority_Conservation_Areas.gpkg"
    translate_geodataframe(priority_public).to_file(zones_gpkg, layer="priority_cells", driver="GPKG", engine="pyogrio")
    if not selected.empty:
        translate_geodataframe(selected_public).to_file(zones_gpkg, layer="priority_cores", driver="GPKG", engine="pyogrio", append=True)
    if not zone_extensions.empty:
        translate_geodataframe(extensions_public).to_file(zones_gpkg, layer="supporting_extensions", driver="GPKG", engine="pyogrio", append=True)
    if not validation_candidates.empty:
        translate_geodataframe(candidates_public).to_file(zones_gpkg, layer="validation_candidates", driver="GPKG", engine="pyogrio", append=True)
    if not zones.empty:
        translate_geodataframe(zones).to_file(zones_gpkg, layer="priority_areas", driver="GPKG", engine="pyogrio", append=True)
        if not operational_evidence_cells.empty:
            translate_geodataframe(operational_evidence_cells).to_file(zones_gpkg, layer="operational_evidence_1km", driver="GPKG", engine="pyogrio", append=True)
        if not operational_zones.empty:
            translate_geodataframe(operational_zones).to_file(zones_gpkg, layer="operational_areas", driver="GPKG", engine="pyogrio", append=True)
        registry.add(zones_gpkg, "21", "Multilayer GeoPackage of planning cells, strategic areas and operational areas")
    else:
        registry.skip("21", "Priority-areas GeoPackage", "No High/Very high cells were selected")

    method = (
        "ECOLOGICAL PRIORITY, MONITORING AND DATA ADEQUACY\n"
        "Conservation priority uses three explicit and complementary pathways: (1) convergence among local richness, temporal persistence, repeated use and repeated representation of low-occupancy species; (2) persistent occurrence cores of a species; and (3) diversity cores.\n"
        "Under the convergence pathway, High requires at least three active families, observations in at least two years, a biodiversity signal, and at least 6 events/6 individuals; Very high requires all four families active, at least three at strong level, ≥3 years, and at least 12 events/12 individuals. The persistent-occurrence pathway can classify a low-richness unit as High when the same species occurs in at least 3 years, 8 independent events and 8 accumulated individuals; a strong core starts at 4 years, 12 events and 12 individuals but does not by itself raise the class to Very high. The diversity pathway classifies as High a unit with at least 4 species, 2 years and 5 events; it also admits exceptional concentrations with at least 5 species, 12 events and 2 repeatedly represented low-occupancy species even with a single year, flagging them for priority temporal validation. A single isolated record can never generate High/Very high priority.\n"
        "LCBD, FDR significance and multiscale hotspots are retained as community-singularity context and never determine selection on their own. Abundance is interpreted together with recurrence and persistence rather than as an autonomous point maximum.\n"
        "If the requested descriptive grid is 1 km, the viewer retains and displays ecological priority calculated at 1 km as a separate descriptive layer, while conservation uses 5 km as the minimum planning unit for strategic priority areas; only the planning grid creates or expands those strategic areas. If 5 or 10 km is requested, the descriptive and planning scales coincide. After strategic delineation, operational conservation areas are derived without recalculating priority from official MITECO 1-km cells containing observations inside each strategic area. Only edge-sharing evidence cells are merged and empty bridge cells are never added, so one strategic area can contain several operational subareas.\n"
        "Temporal signal creates an independent monitoring priority and data adequacy is calculated separately. Neither lowers conservation priority by itself.\n"
        "Sensitivity compares three weightings of the same four families: balanced (25/25/25/25), biodiversity focus (35/20/10/35), and persistence focus (20/35/30/15), while retaining the same minimum convergence gates.\n"
        "Priority areas always originate from High/Very-high cores. A Medium unit may be incorporated only as a supporting extension when it shares a true edge with a core and has ecological score ≥37.5, ≥2 observed years, ≥4 events and ≥2 active ecological-evidence families. Extensions are evaluated in a single ring: they cannot create areas on their own or recruit further extensions, and they never alter the area ecological class, which is calculated only from the cores. Isolated Medium units with score ≥50 and the same minimum support are exported separately as validation candidates and do not form part of a priority area.\n"
        "The multiscale analysis directly uses the official 1, 5, and 10-km MITECO grids; no synthetic Cartesian grid or ecological crosswalk enters the main calculation.\n"
        "Area and protected percentage use the same validated marine geometry. When no valid protection layer exists, status is 'not_evaluated' and is never interpreted as 0% protected.\n"
        + ("Available protected-area sources were clipped to the marine mask and audited file by file.\n" if protected is not None else "No valid protected-area layer was found; the protection gap remains explicitly not evaluated.\n")
        + "This product is a technical screening relative to the current run and requires ecological, spatial, and regulatory validation before management decisions.\n"
    )
    method_path = text_file(method, note_dir / "Methodological_Note_Priority_Areas.txt")
    registry.add(method_path, "21", "Prioritisation methodological note")

    plot_data = priority.to_crs(4326)
    priority_points = priority[["ecological_priority_class", "geometry"]].copy()
    priority_points.geometry = priority_points.geometry.centroid
    priority_points = priority_points.to_crs(4326)
    marker_sizes = {ECO_NOT_EVALUABLE: 5, "Sin capacidad de discriminación": 6, "Baja": 7, "Media": 11, "Alta": 18, "Muy alta": 28}
    fig, ax = plt.subplots(figsize=(11, 8.5))
    add_map_context(ax, cartographic_context)
    for ecological_class in [ECO_NOT_EVALUABLE, "Sin capacidad de discriminación", "Baja", "Media", "Alta", "Muy alta"]:
        subset = plot_data[plot_data["ecological_priority_class"].eq(ecological_class)]
        if not subset.empty:
            subset.plot(ax=ax, color=PRIORITY_COLORS[ecological_class], edgecolor="white", linewidth=0.15, label=ecological_class, zorder=2)
            priority_points[
                priority_points["ecological_priority_class"].eq(ecological_class)
            ].plot(
                ax=ax,
                color=PRIORITY_COLORS[ecological_class],
                edgecolor="#454545",
                linewidth=0.25,
                markersize=marker_sizes[ecological_class],
                zorder=3,
            )
    if not zones.empty:
        zones.to_crs(4326).boundary.plot(ax=ax, color="#00a6a6", linewidth=0.45, zorder=4)
    handles = [
        Patch(facecolor=PRIORITY_COLORS[label], edgecolor="white", label=translate_text(label))
        for label in (ECO_NOT_EVALUABLE, "Sin capacidad de discriminación", "Baja", "Media", "Alta", "Muy alta")
        if priority["ecological_priority_class"].eq(label).any()
    ]
    ax.legend(handles=handles, title="Priority")
    ax.set(title="Hispa-Syng v1.0 — Priority conservation areas", xlabel="Longitude", ylabel="Latitude")
    figure_paths = save_figure(fig, figure_dir / "Map_21_Priority_Conservation_Areas")
    for path in figure_paths:
        registry.add(path, "21", "Static priority-areas map")
    map_png = next(path for path in figure_paths if path.suffix == ".png")
    selected_map_png = map_png
    fig, ax = plt.subplots(figsize=(11, 8.5))
    add_map_context(ax, cartographic_context)
    if not zone_extensions.empty:
        zone_extensions.to_crs(4326).plot(
            ax=ax, facecolor="#d9e7e7", edgecolor="#4f8f8f", linewidth=0.35, zorder=1
        )
    if not selected.empty:
        for ecological_class in ["Alta", "Muy alta"]:
            subset = selected[selected["ecological_priority_class"].eq(ecological_class)]
            if not subset.empty:
                subset.to_crs(4326).plot(
                    ax=ax, color=PRIORITY_COLORS[ecological_class], edgecolor="white",
                    linewidth=0.20, zorder=2,
                )
    if not validation_candidates.empty:
        validation_candidates.to_crs(4326).boundary.plot(
            ax=ax, color="#a6611a", linewidth=0.7, linestyle="--", zorder=3
        )
    if not zones.empty:
        zones.to_crs(4326).boundary.plot(ax=ax, color="#007f7f", linewidth=0.65, zorder=4)
    selected_handles = [
        Patch(facecolor=PRIORITY_COLORS[label], edgecolor="white", label=f"Priority core — {translate_text(label)}")
        for label in ["Alta", "Muy alta"] if selected["ecological_priority_class"].eq(label).any()
    ]
    if not zone_extensions.empty:
        selected_handles.append(Patch(facecolor="#d9e7e7", edgecolor="#4f8f8f", label="Medium supporting extension"))
    if not validation_candidates.empty:
        selected_handles.append(Patch(facecolor="none", edgecolor="#a6611a", label="Medium validation candidate"))
    if selected_handles:
        ax.legend(handles=selected_handles, title="Conservation role")
    ax.set_title("Priority areas: cores, supporting extensions and candidates")
    ax.set(xlabel="Longitude", ylabel="Latitude")
    selected_outputs = save_figure(fig, figure_dir / "Map_21_Selected_Priority_Areas")
    selected_map_png = next(output for output in selected_outputs if output.suffix == ".png")
    for output in selected_outputs:
        registry.add(output, "21", "Static map of selected priority areas")

    priority_for_map = _cells_with_species_summary_for_map(priority, conservation_assigned)
    descriptive_for_map = (
        _cells_with_species_summary_for_map(descriptive_priority, descriptive_assigned)
        if descriptive_priority is not None and not descriptive_priority.empty
        else gpd.GeoDataFrame()
    )
    zones_for_map = _zones_with_species_summary_for_map(zones, zone_cells, conservation_assigned)
    conservation_html_context = dict(html_context)
    conservation_html_context["planning_grid_km"] = int(planning_grid_km)
    conservation_html_context["requested_grid_km"] = int(selected_grid_km)
    html_path = _interactive_map(
        priority_for_map,
        descriptive_for_map,
        zones_for_map,
        operational_zones,
        protected,
        map_dir / conservation_html_name(selected_grid_km),
        cartographic_context,
        conservation_html_context,
        marine_mask,
    )
    registry.add(
        html_path,
        "21",
        f"Single interactive map of prioritisation, areas, and protection ({selected_grid_km} km)",
    )
    LOGGER.info("    [7/8 · 5/5] Conservation maps, spatial data, and report")
    report_path = _word_report(
        priority,
        zone_summary,
        operational_summary,
        selected_map_png,
        logo_path,
        root / "Hispa_Syng_Priority_Areas_Report.docx",
        html_context,
    )
    registry.add(report_path, "21", "Priority-areas Word report")
    return {
        "priority_grid": priority,
        "descriptive_priority_grid": descriptive_priority,
        "selected_cells": selected,
        "zone_cells": zone_cells,
        "zone_extensions": zone_extensions,
        "validation_candidates": validation_candidates,
        "zones": zones,
        "zone_summary": zone_summary,
        "operational_zones": operational_zones,
        "operational_zone_summary": operational_summary,
        "operational_evidence_cells": operational_evidence_cells,
        # Keep the already validated local cartographic context available to
        # the integrated report.  The report is generated after this block
        # and must not depend on the optional ``basemap`` package or on an
        # online tile service to draw land and coastline.
        "map_context": cartographic_context,
        "protected_areas": protected,
        "protected_areas_loaded": protected is not None,
        "protected_layer_name": "areas_protegidas_sf_marinas" if protected is not None else None,
        "spatial_qa": spatial_qa,
        "interactive_map": html_path,
        "report": report_path,
    }
