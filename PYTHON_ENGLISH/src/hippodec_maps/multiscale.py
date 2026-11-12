"""Official MITECO multiscale community and hotspot analysis (1, 5, 10 km)."""

from __future__ import annotations

from pathlib import Path
import logging
from typing import Any

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats
from sklearn.cluster import DBSCAN

from .analysis_io import OutputRegistry, csv2, excel_book, finite_quantile, mode_or_na, save_figure, table_pair, text_file
from .analysis_utils import (
    AnalysisSettings,
    bray_curtis_matrix,
    euclidean_matrix,
    hellinger,
    jaccard_matrix,
    lcbd,
    mantel_spearman,
    moran_i,
)
from .cartography import MapContext, add_map_context
from .localization import translate_geodataframe
from .spatial import assign_points_to_grid, official_grid_relation

LOGGER = logging.getLogger("hippodec_maps")

LANGUAGE = "en"
SCALES_KM = (10, 5, 1)
REQUESTED_SCALES = (1, 5, 10)
PERSISTENCE_COLORS = {0: "#d9d9d9", 1: "#fee08b", 2: "#f46d43", 3: "#a50026"}
LABELS = {'persistence_title': 'Multiscale hotspot persistence', 'longitude': 'Longitude', 'latitude': 'Latitude', 'persistence_0': '0 · no hotspot', 'persistence_1': '1 scale', 'persistence_2': '2 scales', 'persistence_3': '3 scales', 'persistence_legend': 'Persistence (number of scales)', 'type_persistent': 'Persistent high and significant hotspot', 'type_multiscale': 'Multiscale high and significant hotspot', 'type_scale': 'Scale-dependent high and significant hotspot', 'type_none': 'No hotspot', 'no_official_cells': 'No official marine cells are available for conservation.', 'duplicate_official_ids': 'Official MITECO grid identifiers are not unique.', 'missing_crs': 'The official conservation grid has no CRS.', 'invalid_marine_geometry': 'The official conservation grid contains empty or invalid marine geometries.', 'invalid_marine_area': 'The official conservation grid contains non-positive marine areas.', 'log_prepare': '    [4/8 · 1/5] Preparing multiscale analysis on official 10, 5 and 1 km MITECO grids', 'log_scale': '    [4/8] Scale %d km: official assignment, event support, LCBD and Mantel', 'grid_unavailable': 'The official {scale} km MITECO grid is unavailable; this scale is not estimable.', 'grid_missing_crs': 'The official {scale} km MITECO grid has no CRS; this scale is not estimable.', 'assignment_failed': 'Official assignment failed at {scale} km', 'few_event_cells': 'Fewer than two cells have ≥{n} observation events.', 'few_incidence_cells': 'Fewer than two cells contain evaluable incidences.', 'grid_lcbd_desc': 'Exact official {scale} km MITECO LCBD grid', 'master_gpkg': 'Multiscale_Hotspot_Master_Grid.gpkg', 'master_desc': 'Selected official {scale} km MITECO grid with multiscale persistence', 'conservation_gpkg': 'Official_MITECO_Conservation_Master_Grid.gpkg', 'conservation_desc': 'Official marine MITECO grid used directly by conservation', 'assignment_qa_csv': 'Debug_12_Official_Multiscale_Assignment.csv', 'hierarchy_csv': 'Debug_12_Official_MITECO_Hierarchy.csv', 'canonical_csv': 'Debug_12_Canonical_Multiscale_Persistence.csv', 'spatial_qa_csv': 'Multiscale_Spatial_Basis_Quality_Control.csv', 'assignment_qa_desc': 'Official-grid assignment control by scale', 'hierarchy_desc': 'Geometric relations among official MITECO scales', 'canonical_desc': 'Persistence on the finest available official canonical support', 'spatial_qa_desc': 'Official multiscale spatial-basis quality controls', 'workbook': 'Tables_12_Multiscale_Analysis.xlsx', 'workbook_desc': 'Official multiscale-analysis workbook', 'table_prefix': 'Table', 'moran_text': 'Observed Moran I: {I}\nExpected I: {expected}\nMonte Carlo p: {p}\nPermutations: {permutations}\n', 'moran_txt': 'Monte_Carlo_Autocorrelation_Test_High_Significant_Hotspot.txt', 'moran_desc': 'Moran Monte Carlo test on official-grid persistence', 'method_note_file': 'Methodological_Note_Multiscale.txt', 'method_note_desc': 'Official multiscale-analysis methodological note', 'method_note': "OFFICIAL MITECO MULTISCALE ANALYSIS\nRequested scales: {scales} km.\nMinimum support: {min_events} observation events per cell; n_records is retained only as descriptive record volume.\nObservations are assigned directly to the official 1/5/10 km MITECO grids using the validated direct/nearest spatial rule and positive Area_mar_km2.\nPrimary LCBD: presence/absence incidence with Jaccard dissimilarity. LCBD>=P90 magnitude remains separate from inferential support.\nPersistence significance: BH-FDR (adjusted p <0.05) plus minimum event support.\nPrimary distance-decay: Mantel-Spearman between incidence Jaccard and geographic distance; the linear slope is descriptive only.\nHellinger->Bray-Curtis is not used. Raw-abundance Bray-Curtis and Hellinger-Euclidean are exported only as coherent sensitivities.\nCanonical persistence support: finest available official grid with records ({canonical} km), independent of the user-selected resolution.\nAll-scale persistence means 3/3 evaluable scales only; a missing/non-estimable scale never redefines 'all scales'.\nAggregation to the selected resolution ({selected} km) uses real geometric relations among official polygons; no cell-centroid sampling and no ecological crosswalk.\n15-km DBSCAN is retained only as a descriptive fixed-radius core, not as management-zone continuity.\nPersistence Moran I: {moran}; Monte Carlo p = {p}.\n", 'richness_title': 'Mean richness by spatial scale', 'scale_xlabel': 'Official MITECO scale (km)', 'richness_ylabel': 'Mean richness per cell', 'richness_fig_desc': 'Multiscale mean-richness figure', 'hotspots_title': 'High LCBD hotspots with BH-FDR support by scale', 'hotspots_ylabel': 'Number of hotspots', 'hotspots_fig_desc': 'FDR-supported LCBD hotspots by scale', 'persistence_fig_desc': 'Official multiscale-persistence map', 'observed': 'Observed', 'moran_title': 'Persistence autocorrelation: Monte Carlo distribution', 'moran_fig_desc': 'Moran Monte Carlo histogram'}


def _label(key: str) -> str:
    return LABELS[key]


def persistence_hotspot_figure(master: gpd.GeoDataFrame, cartographic_context: MapContext) -> plt.Figure:
    """Draw the selected official grid with multiscale-persistence symbols."""
    fig, ax = plt.subplots(figsize=(10, 8))
    add_map_context(ax, cartographic_context)
    if master.empty:
        ax.set(title=_label("persistence_title"), xlabel=_label("longitude"), ylabel=_label("latitude"))
        return fig

    polygons = master.to_crs(4326).copy()
    persistence = pd.to_numeric(master.get("hotspot_persistence"), errors="coerce").fillna(0).clip(lower=0).round().astype(int)
    centers = master[["geometry"]].copy()
    centers.geometry = centers.geometry.centroid
    centers["hotspot_persistence"] = persistence.to_numpy()
    centers = centers.to_crs(4326)
    polygons.boundary.plot(ax=ax, color="#7a858d", linewidth=0.25, alpha=0.65, zorder=2)
    marker_sizes = {0: 10, 1: 34, 2: 50, 3: 68}
    for value in range(4):
        subset = centers[centers["hotspot_persistence"].eq(value)]
        if subset.empty:
            continue
        subset.plot(
            ax=ax,
            marker="s",
            color=PERSISTENCE_COLORS[value],
            edgecolor="#3f474d" if value else "#7a858d",
            linewidth=0.35 if value else 0.2,
            markersize=marker_sizes[value],
            alpha=0.95 if value else 0.7,
            zorder=4 if value else 3,
        )
    labels = {0: _label("persistence_0"), 1: _label("persistence_1"), 2: _label("persistence_2"), 3: _label("persistence_3")}
    handles = [Patch(facecolor=PERSISTENCE_COLORS[value], edgecolor="#3f474d", label=labels[value]) for value in range(4)]
    ax.legend(handles=handles, title=_label("persistence_legend"), loc="lower right")
    ax.set(title=_label("persistence_title"), xlabel=_label("longitude"), ylabel=_label("latitude"))
    return fig


def _empty_scale_summary(scale_km: int, status: str, detail: str) -> dict[str, Any]:
    return {
        "scale_km": int(scale_km),
        "analysis_status": status,
        "status_detail": detail,
        "n_cells_total_with_records": 0,
        "n_cells_evaluable": 0,
        "n_records": 0,
        "n_sampling_events": 0,
        "mean_records_cell": np.nan,
        "mean_events_cell": np.nan,
        "mean_richness": np.nan,
        "mean_occupancy_pct": np.nan,
        "mean_beta_jaccard_pa": np.nan,
        "max_LCBD": np.nan,
        "n_LCBD_significant": 0,
        "n_LCBD_significant_FDR": 0,
        "n_hotspots": 0,
        "n_hotspots_significant_raw": 0,
        "n_hotspots_significant": 0,
        "distance_decay_method": "Mantel Spearman; Jaccard incidence vs geographic distance",
        "distance_decay_mantel_rho": np.nan,
        "distance_decay_mantel_p_value": np.nan,
        "distance_decay_permutations": 0,
        "distance_decay_slope_per_km": np.nan,
        "distance_decay_p_value": np.nan,
        "distance_decay_R2": np.nan,
    }


def _clean_points_for_reassignment(points: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Remove selected-grid attributes before assigning an official scale."""
    generated = {
        "grid_id", "official_cell_code", "Area_mar_km2", "grid_order", "official_marine_flag",
        "Area_mar_oficial_km2", "Area_mar_gshhs_km2", "Area_celda_km2", "Area_mar_source",
        "Region_slug_cell", "Region_MITECO_cell", "dist_to_cell_m", "assignment_method",
        "Region_slug_direct", "Region_MITECO_direct", "region_cell_disagreement",
        "region_assignment_method", "index_right",
    }
    columns = [column for column in points.columns if column not in generated]
    return gpd.GeoDataFrame(points[columns].copy(), geometry="geometry", crs=points.crs)


def _polygon_adjacency(grid: gpd.GeoDataFrame) -> np.ndarray:
    """Queen-style adjacency on official polygons; no synthetic row/column indices."""
    if grid is None or grid.empty:
        return np.zeros((0, 0), dtype=float)
    work = grid[["geometry"]].reset_index(drop=True)
    n = len(work)
    adjacency = np.zeros((n, n), dtype=float)
    spatial_index = work.sindex
    for i, geom in enumerate(work.geometry):
        if geom is None or geom.is_empty:
            continue
        for j in spatial_index.query(geom, predicate="intersects"):
            j = int(j)
            if j == i:
                continue
            other = work.geometry.iloc[j]
            # Official cells should touch at an edge/corner. Intersects is retained
            # as a robust fallback for tiny topology imperfections.
            if geom.touches(other) or geom.intersects(other):
                adjacency[i, j] = 1.0
                adjacency[j, i] = 1.0
    return adjacency


def _geographic_distance_matrix(grid: gpd.GeoDataFrame, ordered_ids: pd.Index) -> np.ndarray:
    geometry = grid.set_index("grid_id_scale").loc[ordered_ids].geometry.centroid
    coords = np.column_stack([geometry.x.to_numpy(dtype=float), geometry.y.to_numpy(dtype=float)])
    differences = coords[:, None, :] - coords[None, :, :]
    return np.sqrt(np.square(differences).sum(axis=2)) / 1000.0


def _scale_cell_lookup(scale_results: dict[int, dict[str, Any]], scale_km: int) -> pd.DataFrame:
    result = scale_results.get(scale_km, {})
    table = pd.DataFrame(result.get("lcbd", pd.DataFrame())).copy()
    if table.empty:
        return pd.DataFrame(columns=["grid_id_scale"]).set_index("grid_id_scale")
    table["grid_id_scale"] = table["grid_id_scale"].astype(str)
    return table.drop_duplicates("grid_id_scale").set_index("grid_id_scale")


def _relations_from_canonical(
    canonical_scale: int,
    canonical_grid: gpd.GeoDataFrame,
    official_grids: dict[int, gpd.GeoDataFrame],
) -> tuple[dict[int, pd.DataFrame], pd.DataFrame]:
    relations: dict[int, pd.DataFrame] = {}
    audit_rows: list[pd.DataFrame] = []
    canonical_ids = canonical_grid["grid_id"].astype(str)
    identity = pd.DataFrame(
        {
            "fine_grid_id": canonical_ids,
            "coarse_grid_id": canonical_ids,
            "mapping_method": "identity_same_official_scale",
            "overlap_area_km2": canonical_grid.geometry.area.to_numpy(dtype=float) / 1_000_000,
            "overlap_pct_fine_geometry": 100.0,
        }
    )
    relations[canonical_scale] = identity
    audit = identity.copy()
    audit["from_scale_km"] = canonical_scale
    audit["to_scale_km"] = canonical_scale
    audit_rows.append(audit)

    for target_scale in REQUESTED_SCALES:
        if target_scale <= canonical_scale or target_scale not in official_grids:
            continue
        relation = official_grid_relation(canonical_grid, official_grids[target_scale])
        relations[target_scale] = relation
        rel_audit = relation.copy()
        rel_audit["from_scale_km"] = canonical_scale
        rel_audit["to_scale_km"] = target_scale
        audit_rows.append(rel_audit)
    combined = pd.concat(audit_rows, ignore_index=True) if audit_rows else pd.DataFrame()
    return relations, combined


def _build_canonical_persistence(
    scale_results: dict[int, dict[str, Any]],
    official_grids: dict[int, gpd.GeoDataFrame],
) -> tuple[gpd.GeoDataFrame, pd.DataFrame, int | None]:
    """Create persistence on the finest available observed official MITECO grid.

    The definition is independent of the grid resolution selected by the user.
    Missing/non-estimable scales remain explicitly non-evaluable and can never
    redefine 'all scales'.
    """
    candidate_scales = [
        scale for scale in REQUESTED_SCALES
        if scale in scale_results and not scale_results[scale].get("grid_with_records", gpd.GeoDataFrame()).empty
    ]
    if not candidate_scales:
        return gpd.GeoDataFrame(), pd.DataFrame(), None
    canonical_scale = min(candidate_scales)
    canonical_grid = scale_results[canonical_scale]["grid_with_records"].copy()
    canonical_grid = canonical_grid.drop_duplicates("grid_id").copy()
    canonical_grid["grid_id"] = canonical_grid["grid_id"].astype(str)
    relations, relation_audit = _relations_from_canonical(canonical_scale, canonical_grid, official_grids)

    master = canonical_grid[[column for column in canonical_grid.columns if column in ("grid_id", "geometry", "Region_slug", "Region_MITECO", "Area_mar_km2")]].copy()
    master = master.rename(columns={"grid_id": "master_id"})
    master["canonical_support_scale_km"] = int(canonical_scale)

    for scale in REQUESTED_SCALES:
        id_col = f"grid_id_{scale}km"
        eval_col = f"scale_evaluable_{scale}km"
        hotspot_col = f"hotspot_{scale}km"
        raw_col = f"hotspot_raw_{scale}km"
        high_col = f"hotspot_high_{scale}km"
        lcbd_col = f"LCBD_{scale}km"
        p_col = f"LCBD_p_adjust_BH_{scale}km"

        if scale < canonical_scale or scale not in official_grids:
            master[id_col] = pd.NA
        else:
            relation = relations.get(scale, pd.DataFrame())
            mapping = relation.set_index("fine_grid_id")["coarse_grid_id"].to_dict() if not relation.empty else {}
            master[id_col] = master["master_id"].astype(str).map(mapping)

        lookup = _scale_cell_lookup(scale_results, scale)
        mapped = master[id_col].astype("string")
        is_eval = mapped.notna() & mapped.isin(lookup.index.astype(str))
        master[eval_col] = is_eval.astype(bool)
        if lookup.empty:
            master[hotspot_col] = pd.Series(pd.NA, index=master.index, dtype="Int64")
            master[raw_col] = pd.Series(pd.NA, index=master.index, dtype="Int64")
            master[high_col] = pd.Series(pd.NA, index=master.index, dtype="Int64")
            master[lcbd_col] = np.nan
            master[p_col] = np.nan
            continue

        def mapped_values(column: str, default=np.nan):
            if column not in lookup.columns:
                return pd.Series(default, index=master.index)
            return mapped.map(lookup[column])

        fdr = mapped_values("hotspot_significant_fdr", False)
        raw = mapped_values("hotspot_significant_raw", False)
        high = mapped_values("hotspot", False)
        # Explicit nullable Boolean semantics preserve missing values without object-dtype coercion
        # downcasting while preserving <NA> for non-evaluable cells.
        fdr_flag = pd.Series(fdr, index=master.index, dtype="boolean").fillna(False).astype("int8")
        raw_flag = pd.Series(raw, index=master.index, dtype="boolean").fillna(False).astype("int8")
        high_flag = pd.Series(high, index=master.index, dtype="boolean").fillna(False).astype("int8")
        eval_mask = is_eval.to_numpy(dtype=bool)
        master[hotspot_col] = pd.Series(np.where(eval_mask, fdr_flag.to_numpy(), pd.NA), index=master.index, dtype="Int64")
        master[raw_col] = pd.Series(np.where(eval_mask, raw_flag.to_numpy(), pd.NA), index=master.index, dtype="Int64")
        master[high_col] = pd.Series(np.where(eval_mask, high_flag.to_numpy(), pd.NA), index=master.index, dtype="Int64")
        master[lcbd_col] = pd.to_numeric(mapped_values("LCBD"), errors="coerce")
        master[p_col] = pd.to_numeric(mapped_values("LCBD_p_adjust_BH"), errors="coerce")

    eval_columns = [f"scale_evaluable_{scale}km" for scale in REQUESTED_SCALES]
    hotspot_columns = [f"hotspot_{scale}km" for scale in REQUESTED_SCALES]
    master["n_scales_evaluable"] = master[eval_columns].astype(int).sum(axis=1)
    hotspot_numeric = pd.concat([pd.to_numeric(master[column], errors="coerce") for column in hotspot_columns], axis=1)
    master["hotspot_persistence"] = hotspot_numeric.fillna(0).sum(axis=1).astype(int)
    master["is_hotspot_any_scale"] = master["hotspot_persistence"].ge(1)
    master["is_hotspot_multiscale"] = master["hotspot_persistence"].ge(2)
    master["is_hotspot_persistent_all_scales"] = master["n_scales_evaluable"].eq(3) & master["hotspot_persistence"].eq(3)
    master["stability_requested_scales_pct"] = 100.0 * master["hotspot_persistence"] / 3.0
    master["stability_evaluable_scales_pct"] = np.where(
        master["n_scales_evaluable"].gt(0),
        100.0 * master["hotspot_persistence"] / master["n_scales_evaluable"],
        np.nan,
    )
    master["stability_pct"] = master["stability_requested_scales_pct"]
    master["hotspot_type"] = np.select(
        [master["is_hotspot_persistent_all_scales"], master["is_hotspot_multiscale"], master["is_hotspot_any_scale"]],
        [_label("type_persistent"), _label("type_multiscale"), _label("type_scale")],
        default=_label("type_none"),
    )
    master["persistence_definition"] = "FDR-supported high LCBD (Jaccard incidence); denominator fixed at requested official scales 1/5/10 km"
    return gpd.GeoDataFrame(master, geometry="geometry", crs=canonical_grid.crs), relation_audit, canonical_scale


def _aggregate_persistence_to_selected(
    canonical: gpd.GeoDataFrame,
    canonical_scale: int | None,
    selected_grid_km: int,
    selected_grid_with_records: gpd.GeoDataFrame,
    official_grids: dict[int, gpd.GeoDataFrame],
) -> gpd.GeoDataFrame:
    """Aggregate canonical fine-grid evidence to the selected official grid.

    Any displaced fine hotspot is retained through a real polygon relation; no
    selected-cell centroid is used to sample a finer grid.
    """
    base = selected_grid_with_records.drop_duplicates("grid_id").copy()
    base["grid_id"] = base["grid_id"].astype(str)
    base = base.rename(columns={"grid_id": "master_id"})
    if canonical_scale is None or canonical.empty:
        base["canonical_support_cells"] = 0
        base["n_scales_evaluable"] = 0
        base["hotspot_persistence"] = np.nan
        for scale in REQUESTED_SCALES:
            base[f"hotspot_{scale}km"] = pd.Series(pd.NA, index=base.index, dtype="Int64")
            base[f"hotspot_{scale}km_fraction"] = np.nan
            base[f"n_support_evaluable_{scale}km"] = 0
        base["is_hotspot_any_scale"] = False
        base["is_hotspot_multiscale"] = False
        base["is_hotspot_persistent_all_scales"] = False
        base["hotspot_type"] = _label("type_none")
        base["persistence_aggregation_method"] = "not_estimable_no_canonical_support"
        return gpd.GeoDataFrame(base, geometry="geometry", crs=selected_grid_with_records.crs)

    if selected_grid_km == canonical_scale:
        support = canonical.drop(columns="geometry", errors="ignore").copy()
        support = support.rename(columns={"master_id": "selected_master_id"})
    else:
        target = official_grids[selected_grid_km]
        canonical_geom = scale_results_grid = official_grids[canonical_scale]
        canonical_ids = set(canonical["master_id"].astype(str))
        canonical_geom = canonical_geom[canonical_geom["grid_id"].astype(str).isin(canonical_ids)].copy()
        relation = official_grid_relation(canonical_geom, target)
        support = canonical.drop(columns="geometry", errors="ignore").merge(
            relation[["fine_grid_id", "coarse_grid_id"]],
            left_on="master_id", right_on="fine_grid_id", how="left",
        )
        support = support.rename(columns={"coarse_grid_id": "selected_master_id"})

    rows: list[dict[str, Any]] = []
    for selected_id, group in support.dropna(subset=["selected_master_id"]).groupby("selected_master_id", observed=True):
        row: dict[str, Any] = {
            "master_id": str(selected_id),
            "canonical_support_scale_km": int(canonical_scale),
            "canonical_support_cells": int(len(group)),
            "hotspot_persistence": float(pd.to_numeric(group["hotspot_persistence"], errors="coerce").max()),
            "hotspot_persistence_mean": float(pd.to_numeric(group["hotspot_persistence"], errors="coerce").mean()),
            "n_scales_evaluable": int(pd.to_numeric(group["n_scales_evaluable"], errors="coerce").max()),
            "persistent_all_scales_fraction": float(group["is_hotspot_persistent_all_scales"].astype(bool).mean()),
            "is_hotspot_any_scale": bool(group["is_hotspot_any_scale"].astype(bool).any()),
            "is_hotspot_multiscale": bool(group["is_hotspot_multiscale"].astype(bool).any()),
            "is_hotspot_persistent_all_scales": bool(group["is_hotspot_persistent_all_scales"].astype(bool).any()),
            "stability_requested_scales_pct": float(pd.to_numeric(group["stability_requested_scales_pct"], errors="coerce").max()),
            "stability_evaluable_scales_pct": float(pd.to_numeric(group["stability_evaluable_scales_pct"], errors="coerce").max()),
            "stability_pct": float(pd.to_numeric(group["stability_pct"], errors="coerce").max()),
        }
        for scale in REQUESTED_SCALES:
            evaluable = group[f"scale_evaluable_{scale}km"].astype(bool)
            n_eval = int(evaluable.sum())
            values = pd.to_numeric(group.loc[evaluable, f"hotspot_{scale}km"], errors="coerce")
            row[f"n_support_evaluable_{scale}km"] = n_eval
            row[f"hotspot_{scale}km_fraction"] = float(values.mean()) if n_eval else np.nan
            row[f"hotspot_{scale}km"] = int(values.fillna(0).gt(0).any()) if n_eval else pd.NA
        row["hotspot_type"] = (
            _label("type_persistent") if row["is_hotspot_persistent_all_scales"]
            else _label("type_multiscale") if row["is_hotspot_multiscale"]
            else _label("type_scale") if row["is_hotspot_any_scale"]
            else _label("type_none")
        )
        rows.append(row)
    aggregation = pd.DataFrame(rows)
    master = base.merge(aggregation, on="master_id", how="left")
    master["canonical_support_cells"] = pd.to_numeric(master.get("canonical_support_cells"), errors="coerce").fillna(0).astype(int)
    for column in ("is_hotspot_any_scale", "is_hotspot_multiscale", "is_hotspot_persistent_all_scales"):
        master[column] = master.get(column, pd.Series(False, index=master.index)).astype("boolean").fillna(False).astype(bool)
    master["hotspot_type"] = master.get("hotspot_type", pd.Series(_label("type_none"), index=master.index)).fillna(_label("type_none"))
    master["persistence_aggregation_method"] = (
        "identity_on_canonical_official_grid" if selected_grid_km == canonical_scale
        else "real_official_polygon_relation; any/fraction of canonical support cells; no centroid sampling"
    )
    return gpd.GeoDataFrame(master, geometry="geometry", crs=selected_grid_with_records.crs)


def _build_official_conservation_master(
    official_marine_cells: gpd.GeoDataFrame,
    community: dict[str, Any],
    selected_persistence: gpd.GeoDataFrame,
    selected_grid_km: int,
    minimum_events_cell: int,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """Build conservation input directly on selected official marine MITECO cells."""
    if official_marine_cells is None or official_marine_cells.empty:
        raise ValueError(_label("no_official_cells"))
    keep = [
        column for column in (
            "grid_id", "official_cell_code", "Area_mar_km2", "Area_mar_oficial_km2",
            "Area_mar_gshhs_km2", "Area_celda_km2", "Area_mar_source", "official_marine_flag",
            "Region_slug", "Region_MITECO", "source_file", "marine_geometry_method",
            "marine_geometry_status", "geometry",
        ) if column in official_marine_cells.columns
    ]
    official = official_marine_cells[keep].copy()
    official["grid_id"] = official["grid_id"].astype(str)
    official = official.drop_duplicates("grid_id")
    if official["grid_id"].duplicated().any():
        raise AssertionError(_label("duplicate_official_ids"))
    if official.crs is None:
        raise ValueError(_label("missing_crs"))
    official.geometry = official.geometry.make_valid()
    invalid_geometry = official.geometry.isna() | official.geometry.is_empty | ~official.geometry.is_valid | official.geometry.area.le(0)
    if invalid_geometry.any():
        raise AssertionError(_label("invalid_marine_geometry"))
    official["Area_geometria_marina_km2"] = official.geometry.area / 1_000_000
    official["Area_mar_km2"] = pd.to_numeric(official.get("Area_mar_km2"), errors="coerce")
    if official["Area_mar_km2"].isna().any() or official["Area_mar_km2"].le(0).any():
        raise AssertionError(_label("invalid_marine_area"))

    frames = []
    for key in ("environment_grid", "indices_cells", "lcbd", "clusters"):
        frame = pd.DataFrame(community.get(key, pd.DataFrame())).drop(columns="geometry", errors="ignore").copy()
        if not frame.empty and "grid_id" in frame:
            frame["grid_id"] = frame["grid_id"].astype(str)
            frame = frame.drop_duplicates("grid_id")
        frames.append(frame)
    environment, indices, lcbd_table, clusters = frames
    master = official.copy()
    for frame in (environment, indices, lcbd_table):
        if not frame.empty:
            duplicate_columns = [c for c in frame.columns if c != "grid_id" and c in master.columns]
            frame = frame.drop(columns=duplicate_columns, errors="ignore")
            master = master.merge(frame, on="grid_id", how="left")
    if not clusters.empty:
        cluster_columns = [c for c in ("grid_id", "community_cluster", "macrocluster", "transition_node") if c in clusters]
        duplicate_columns = [c for c in cluster_columns if c != "grid_id" and c in master.columns]
        master = master.merge(clusters[cluster_columns].drop(columns=duplicate_columns, errors="ignore"), on="grid_id", how="left")

    persistence = pd.DataFrame(selected_persistence.drop(columns="geometry", errors="ignore")).copy()
    persistence["master_id"] = persistence["master_id"].astype(str)
    persistence_columns = [c for c in persistence.columns if c == "master_id" or c.startswith("hotspot_") or c.startswith("is_hotspot_") or c.startswith("stability_") or c.startswith("n_scales_") or c.startswith("canonical_") or c.startswith("persistent_") or c.startswith("n_support_") or c in ("hotspot_type", "persistence_aggregation_method")]
    duplicate_persistence = [c for c in persistence_columns if c != "master_id" and c in master.columns]
    persistence_for_merge = persistence[persistence_columns].drop(columns=duplicate_persistence, errors="ignore").rename(columns={"master_id": "grid_id"})
    master = master.merge(persistence_for_merge, on="grid_id", how="left")
    master = gpd.GeoDataFrame(master, geometry="geometry", crs=official.crs)

    # Conservation receives every occupied official marine cell,
    # including cells whose LCBD or event support is not estimable. Otherwise
    # "No evaluable / insufficient data" would disappear before prioritisation.
    # Sampling events are the canonical support unit; record counts are retained
    # only as descriptors and are never substituted as analytical support.
    support = pd.to_numeric(master.get("n_sampling_events"), errors="coerce")
    support_basis = "n_sampling_events" if "n_sampling_events" in master.columns else "not_available"
    master["multiscale_support_basis"] = support_basis
    master["multiscale_support_evaluable"] = support.ge(minimum_events_cell).fillna(False)
    master["master_id"] = master["grid_id"].astype(str)
    master["selected_grid_km"] = int(selected_grid_km)
    master["conservation_grid_source"] = "official_miteco_selected_grid_direct_multiscale"
    if "hotspot_lcbd_fdr" in master:
        master["hotspot_lcbd"] = master["hotspot_lcbd_fdr"].astype("boolean").fillna(False).astype(bool)
    else:
        master["hotspot_lcbd"] = master.get("hotspot_lcbd", pd.Series(False, index=master.index)).astype("boolean").fillna(False).astype(bool)
    for column in ("is_hotspot_any_scale", "is_hotspot_multiscale", "is_hotspot_persistent_all_scales"):
        master[column] = master.get(column, pd.Series(False, index=master.index)).astype("boolean").fillna(False).astype(bool)
    master["richness"] = pd.to_numeric(master.get("richness"), errors="coerce")
    master["abundance"] = pd.to_numeric(master.get("abundance"), errors="coerce")

    matched = master.get("canonical_support_cells", pd.Series(0, index=master.index)).fillna(0).gt(0)
    qa = pd.DataFrame([
        {"check": "official_grid_unique_ids", "status": "PASS", "detail": int(master["master_id"].nunique())},
        {"check": "official_marine_geometries_valid", "status": "PASS", "detail": int(len(master))},
        {"check": "official_marine_area_positive", "status": "PASS", "detail": int(master["Area_mar_km2"].gt(0).sum())},
        {"check": "selected_grid_persistence_direct_join", "status": "PASS" if bool(matched.all()) or master.empty else "WARN", "detail": f"{int(matched.sum())}/{len(master)}"},
        {"check": "synthetic_cartesian_grid_absent", "status": "PASS", "detail": "official MITECO grids only"},
        {"check": "ecological_hotspot_crosswalk_absent", "status": "PASS", "detail": "relations depend only on official geometry/IDs"},
    ])
    return master, qa


def _moran_null_distribution(values: pd.Series, adjacency: np.ndarray, permutations: int, seed: int) -> pd.DataFrame:
    current = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    keep = np.isfinite(current)
    current = current[keep]
    weights = adjacency[np.ix_(keep, keep)] if len(adjacency) else adjacency
    if len(current) < 3 or weights.sum() <= 0 or np.allclose(current, current[0]):
        return pd.DataFrame(columns=["permutation", "Moran_I"])
    total_w = weights.sum()
    def value(x: np.ndarray) -> float:
        centered = x - x.mean()
        denominator = np.sum(centered ** 2)
        if denominator <= 0:
            return np.nan
        return float((len(x) / total_w) * np.sum(weights * np.outer(centered, centered)) / denominator)
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "permutation": np.arange(1, permutations + 1),
        "Moran_I": [value(rng.permutation(current)) for _ in range(permutations)],
    })


def run_multiscale_analysis(
    assigned: gpd.GeoDataFrame,
    directories: dict[str, Path],
    settings: AnalysisSettings,
    registry: OutputRegistry,
    cartographic_context: MapContext,
    selected_grid_km: int,
    official_marine_cells: gpd.GeoDataFrame,
    community: dict[str, Any],
    official_multiscale_grids: dict[int, gpd.GeoDataFrame] | None = None,
    nearest_tolerance_factor: float = 1.0,
) -> dict[str, Any]:
    LOGGER.info(_label("log_prepare"))
    table_dir = directories["04_tablas"] / "multiscale"
    figure_dir = directories["05_figuras"] / "multiscale"
    model_dir = directories["06_modelos"] / "multiscale"
    grid_dir = directories["02_intermedios"] / "mallas_lcbd_multiescala"
    grid_dir.mkdir(parents=True, exist_ok=True)

    official_grids = {int(k): v.copy() for k, v in (official_multiscale_grids or {}).items() if v is not None and not v.empty}
    if int(selected_grid_km) not in official_grids and official_marine_cells is not None and not official_marine_cells.empty:
        official_grids[int(selected_grid_km)] = official_marine_cells.copy()

    base_points = _clean_points_for_reassignment(assigned)
    if "sampling_event_id" not in base_points.columns:
        # Fallback for standalone module use; the standard workflow creates this centrally.
        base_points["sampling_event_id"] = "record_" + base_points["obs_id"].astype(str)
        event_proxy_status = "record_id_fallback"
    else:
        event_proxy_status = "sampling_event_id"

    scale_results: dict[int, dict[str, Any]] = {}
    summaries: list[dict[str, Any]] = []
    richness_all: list[pd.DataFrame] = []
    occupancy_all: list[pd.DataFrame] = []
    effort_all: list[pd.DataFrame] = []
    lcbd_all: list[pd.DataFrame] = []
    distance_decay_all: list[pd.DataFrame] = []
    assignment_qa_rows: list[dict[str, Any]] = []

    for scale_index, scale_km in enumerate(SCALES_KM):
        LOGGER.info(_label("log_scale"), scale_km)
        grid = official_grids.get(scale_km)
        if grid is None or grid.empty:
            detail = _label("grid_unavailable").format(scale=scale_km)
            summaries.append(_empty_scale_summary(scale_km, "not_estimable_grid_unavailable", detail))
            scale_results[scale_km] = {"status": "not_estimable_grid_unavailable", "detail": detail, "grid_with_records": gpd.GeoDataFrame(), "lcbd": pd.DataFrame()}
            assignment_qa_rows.append({"scale_km": scale_km, "status": "WARN", "analysis_status": "not_estimable_grid_unavailable", "points_total": len(base_points), "points_assigned": 0, "points_unassigned": len(base_points), "support_basis": event_proxy_status, "detail": detail})
            registry.skip("12", f"{scale_km} km", detail)
            continue
        if grid.crs is None:
            detail = _label("grid_missing_crs").format(scale=scale_km)
            summaries.append(_empty_scale_summary(scale_km, "not_estimable_grid_invalid", detail))
            scale_results[scale_km] = {"status": "not_estimable_grid_invalid", "detail": detail, "grid_with_records": gpd.GeoDataFrame(), "lcbd": pd.DataFrame()}
            assignment_qa_rows.append({"scale_km": scale_km, "status": "WARN", "analysis_status": "not_estimable_grid_invalid", "points_total": len(base_points), "points_assigned": 0, "points_unassigned": len(base_points), "support_basis": event_proxy_status, "detail": detail})
            registry.skip("12", f"{scale_km} km", detail)
            continue

        points_for_scale = base_points.to_crs(grid.crs) if base_points.crs != grid.crs else base_points.copy()
        try:
            scale_assigned, unassigned, assignment_stats = assign_points_to_grid(
                points_for_scale,
                grid,
                tolerance_m=float(scale_km) * 1000.0 * float(nearest_tolerance_factor),
            )
        except Exception as exc:
            detail = f"{_label('assignment_failed').format(scale=scale_km)}: {exc}"
            summaries.append(_empty_scale_summary(scale_km, "not_estimable_assignment_failed", detail))
            scale_results[scale_km] = {"status": "not_estimable_assignment_failed", "detail": detail, "grid_with_records": gpd.GeoDataFrame(), "lcbd": pd.DataFrame()}
            assignment_qa_rows.append({"scale_km": scale_km, "status": "WARN", "analysis_status": "not_estimable_assignment_failed", "points_total": len(base_points), "points_assigned": 0, "points_unassigned": len(base_points), "support_basis": event_proxy_status, "detail": detail})
            registry.skip("12", f"{scale_km} km", detail)
            continue

        scale_assigned["grid_id_scale"] = scale_assigned["grid_id"].astype(str)
        scale_assigned["N_aux"] = pd.to_numeric(scale_assigned.get("N_total"), errors="coerce").fillna(0).clip(lower=0)
        scale_assigned["Depth_aux"] = pd.to_numeric(scale_assigned.get("Depth"), errors="coerce")
        scale_assigned["Habitat_aux"] = scale_assigned.get("Habitat", pd.Series(pd.NA, index=scale_assigned.index)).astype("string").str.strip()
        if "year" not in scale_assigned.columns:
            date_col = "Date of observation" if "Date of observation" in scale_assigned.columns else None
            scale_assigned["year"] = pd.to_datetime(scale_assigned[date_col], errors="coerce").dt.year if date_col else np.nan

        effort = (
            scale_assigned.groupby("grid_id_scale", observed=True)
            .agg(
                n_records=("grid_id_scale", "size"),
                n_sampling_events=("sampling_event_id", "nunique"),
                n_years_observed=("year", "nunique"),
                abundance=("N_aux", "sum"),
                richness=("Species", "nunique"),
                depth_median=("Depth_aux", "median"),
                n_depth_valid=("Depth_aux", "count"),
                habitat_dominant=("Habitat_aux", mode_or_na),
            )
            .reset_index()
        )
        effort["scale_km"] = scale_km
        effort["records_per_event"] = effort["n_records"] / effort["n_sampling_events"].replace(0, np.nan)
        observed_ids = set(effort["grid_id_scale"].astype(str))
        grid_with_records = grid[grid["grid_id"].astype(str).isin(observed_ids)].copy()
        grid_with_records["grid_id"] = grid_with_records["grid_id"].astype(str)
        grid_with_records = grid_with_records.drop_duplicates("grid_id")
        grid_with_records = grid_with_records.merge(effort, left_on="grid_id", right_on="grid_id_scale", how="left")
        grid_with_records = gpd.GeoDataFrame(grid_with_records, geometry="geometry", crs=grid.crs)

        assignment_qa_rows.append({
            "scale_km": scale_km,
            "status": "PASS" if len(unassigned) == 0 else "WARN",
            "analysis_status": "assigned",
            "points_total": int(assignment_stats.get("points_total", len(base_points))),
            "points_assigned": int(assignment_stats.get("points_assigned", len(scale_assigned))),
            "points_unassigned": int(len(unassigned)),
            "assignment_intersects": int(assignment_stats.get("points_intersects", 0)),
            "assignment_nearest": int(assignment_stats.get("points_nearest", 0)),
            "grid_cells_valid_marine": int(assignment_stats.get("grid_cells_valid_marine", 0)),
            "support_basis": event_proxy_status,
            "detail": "official MITECO direct/nearest assignment",
        })

        evaluable_ids = set(effort.loc[effort["n_sampling_events"].ge(settings.min_records_cell), "grid_id_scale"].astype(str))
        evaluated = scale_assigned[scale_assigned["grid_id_scale"].isin(evaluable_ids)].copy()
        if len(evaluable_ids) < 2:
            detail = _label("few_event_cells").format(n=settings.min_records_cell)
            summary = _empty_scale_summary(scale_km, "not_estimable_insufficient_event_supported_cells", detail)
            summary.update({
                "n_cells_total_with_records": int(len(effort)),
                "n_records": int(effort["n_records"].sum()),
                "n_sampling_events": int(effort["n_sampling_events"].sum()),
                "mean_records_cell": float(effort["n_records"].mean()) if len(effort) else np.nan,
                "mean_events_cell": float(effort["n_sampling_events"].mean()) if len(effort) else np.nan,
            })
            summaries.append(summary)
            richness_all.append(effort[["grid_id_scale", "richness", "n_records", "n_sampling_events", "abundance", "scale_km"]].copy())
            effort_all.append(effort)
            scale_results[scale_km] = {
                "status": "not_estimable_insufficient_event_supported_cells", "detail": detail,
                "points": evaluated, "grid": gpd.GeoDataFrame(), "grid_all": grid_with_records,
                "grid_with_records": grid_with_records, "matrix": pd.DataFrame(), "abundance_matrix": pd.DataFrame(),
                "lcbd": pd.DataFrame(), "assignment_qa": assignment_stats, "unassigned": unassigned,
            }
            registry.skip("12", f"LCBD {scale_km} km", detail)
            continue

        evaluated["_presence"] = 1
        incidence = evaluated.pivot_table(index="grid_id_scale", columns="Species", values="_presence", aggfunc="max", fill_value=0).astype(float)
        abundance_matrix = evaluated.pivot_table(index="grid_id_scale", columns="Species", values="N_aux", aggfunc="sum", fill_value=0).astype(float)
        abundance_matrix = abundance_matrix.reindex(index=incidence.index, columns=incidence.columns, fill_value=0)
        if len(incidence) < 2:
            detail = _label("few_incidence_cells")
            summary = _empty_scale_summary(scale_km, "not_estimable_insufficient_incidence_cells", detail)
            summary.update({"n_cells_total_with_records": int(len(effort)), "n_cells_evaluable": int(len(incidence)), "n_records": int(effort["n_records"].sum()), "n_sampling_events": int(effort["n_sampling_events"].sum())})
            summaries.append(summary)
            effort_all.append(effort)
            scale_results[scale_km] = {"status": "not_estimable_insufficient_incidence_cells", "detail": detail, "points": evaluated, "grid": gpd.GeoDataFrame(), "grid_all": grid_with_records, "grid_with_records": grid_with_records, "matrix": incidence, "abundance_matrix": abundance_matrix, "lcbd": pd.DataFrame(), "assignment_qa": assignment_stats, "unassigned": unassigned}
            registry.skip("12", f"LCBD {scale_km} km", detail)
            continue

        lcbd_table = lcbd(incidence, settings.permutations, settings.random_seed + 100 + scale_index, method="jaccard").rename(columns={"grid_id": "grid_id_scale", "LCBD_significant": "LCBD_significant_raw"})
        lcbd_table["grid_id_scale"] = lcbd_table["grid_id_scale"].astype(str)
        threshold = finite_quantile(lcbd_table["LCBD"], 0.90, np.inf)
        lcbd_table = lcbd_table.merge(effort[["grid_id_scale", "n_records", "n_sampling_events", "n_years_observed"]], on="grid_id_scale", how="left", validate="one_to_one")
        lcbd_table["support_events_ge_min"] = pd.to_numeric(lcbd_table["n_sampling_events"], errors="coerce").ge(settings.min_records_cell)
        lcbd_table["hotspot"] = lcbd_table["LCBD"].ge(threshold)
        lcbd_table["hotspot_significant_raw"] = lcbd_table["hotspot"] & lcbd_table["LCBD_significant_raw"] & lcbd_table["support_events_ge_min"]
        lcbd_table["hotspot_significant_fdr"] = lcbd_table["hotspot"] & lcbd_table["LCBD_significant_FDR"] & lcbd_table["support_events_ge_min"]
        # Internal field: 'significant' means BH-FDR-supported.
        lcbd_table["hotspot_significant"] = lcbd_table["hotspot_significant_fdr"]
        lcbd_table["scale_km"] = scale_km
        lcbd_table["hotspot_threshold_p90"] = threshold

        grid_eval = grid_with_records[grid_with_records["grid_id"].isin(set(incidence.index.astype(str)))].copy()
        lcbd_merge = lcbd_table.drop(columns=[c for c in ("n_records", "n_sampling_events", "n_years_observed") if c in lcbd_table], errors="ignore")
        grid_eval = grid_eval.merge(lcbd_merge, on=["grid_id_scale", "scale_km"], how="inner", validate="one_to_one")
        grid_eval = gpd.GeoDataFrame(grid_eval, geometry="geometry", crs=grid.crs)

        presence = incidence.astype(int)
        occupancy = presence.sum(axis=0).rename("occupied_cells").reset_index()
        occupancy["occupancy_pct"] = 100 * occupancy["occupied_cells"] / len(incidence)
        occupancy["scale_km"] = scale_km
        richness = effort[effort["grid_id_scale"].isin(incidence.index)][["grid_id_scale", "richness", "n_records", "n_sampling_events", "abundance"]].copy()
        richness["scale_km"] = scale_km

        jaccard = jaccard_matrix(incidence.to_numpy(dtype=float))
        raw_bray = bray_curtis_matrix(abundance_matrix.to_numpy(dtype=float))
        hellinger_euclidean = euclidean_matrix(hellinger(abundance_matrix.to_numpy(dtype=float)))
        geo_distance = _geographic_distance_matrix(grid_eval, incidence.index)
        mantel = mantel_spearman(jaccard, geo_distance, settings.permutations, settings.random_seed + 200 + scale_index)

        pair_rows: list[dict[str, Any]] = []
        for i, first in enumerate(incidence.index):
            for j in range(i + 1, len(incidence)):
                pair_rows.append({
                    "scale_km": scale_km,
                    "grid_1": str(first),
                    "grid_2": str(incidence.index[j]),
                    "distance_km": float(geo_distance[i, j]),
                    "similarity_jaccard_incidence": float(1 - jaccard[i, j]),
                    "dissimilarity_jaccard_incidence": float(jaccard[i, j]),
                    "dissimilarity_bray_raw_abundance_sensitivity": float(raw_bray[i, j]),
                    "distance_hellinger_euclidean_sensitivity": float(hellinger_euclidean[i, j]),
                })
        decay = pd.DataFrame(pair_rows)
        if len(decay) >= 3 and decay[["distance_km", "similarity_jaccard_incidence"]].nunique().min() > 1:
            regression = stats.linregress(decay["distance_km"], decay["similarity_jaccard_incidence"])
            slope, decay_r2 = float(regression.slope), float(regression.rvalue ** 2)
        else:
            slope, decay_r2 = np.nan, np.nan

        upper = jaccard[np.triu_indices(len(jaccard), 1)]
        summary = {
            "scale_km": scale_km,
            "analysis_status": "estimable",
            "status_detail": "official MITECO grid; event-supported incidence LCBD",
            "n_cells_total_with_records": int(len(effort)),
            "n_cells_evaluable": int(len(incidence)),
            "n_records": int(effort["n_records"].sum()),
            "n_sampling_events": int(effort["n_sampling_events"].sum()),
            "mean_records_cell": float(effort.loc[effort["grid_id_scale"].isin(incidence.index), "n_records"].mean()),
            "mean_events_cell": float(effort.loc[effort["grid_id_scale"].isin(incidence.index), "n_sampling_events"].mean()),
            "mean_richness": float(richness["richness"].mean()),
            "mean_occupancy_pct": float(occupancy["occupancy_pct"].mean()),
            "mean_beta_jaccard_pa": float(np.mean(upper)) if len(upper) else np.nan,
            "max_LCBD": float(lcbd_table["LCBD"].max()),
            "n_LCBD_significant": int(lcbd_table["LCBD_significant_raw"].sum()),
            "n_LCBD_significant_FDR": int(lcbd_table["LCBD_significant_FDR"].sum()),
            "n_hotspots": int(lcbd_table["hotspot"].sum()),
            "n_hotspots_significant_raw": int(lcbd_table["hotspot_significant_raw"].sum()),
            "n_hotspots_significant": int(lcbd_table["hotspot_significant_fdr"].sum()),
            "distance_decay_method": mantel["method"],
            "distance_decay_mantel_rho": mantel["mantel_rho"],
            "distance_decay_mantel_p_value": mantel["mantel_p_value"],
            "distance_decay_permutations": mantel["permutations"],
            "distance_decay_slope_per_km": slope,
            "distance_decay_p_value": mantel["mantel_p_value"],
            "distance_decay_R2": decay_r2,
        }
        summaries.append(summary)
        richness_all.append(richness)
        occupancy_all.append(occupancy)
        effort_all.append(effort)
        lcbd_all.append(lcbd_table)
        distance_decay_all.append(decay)
        scale_results[scale_km] = {
            "status": "estimable", "detail": summary["status_detail"], "points": evaluated,
            "grid": grid_eval, "grid_all": grid_with_records, "grid_with_records": grid_with_records,
            "matrix": incidence, "abundance_matrix": abundance_matrix, "lcbd": lcbd_table,
            "assignment_qa": assignment_stats, "unassigned": unassigned,
            "jaccard_distance": jaccard, "bray_raw_abundance_sensitivity": raw_bray,
            "hellinger_euclidean_sensitivity": hellinger_euclidean, "mantel": mantel,
        }
        gpkg = grid_dir / f"malla_lcbd_multiescala_{scale_km}km.gpkg"
        translate_geodataframe(grid_eval).to_file(gpkg, layer=f"malla_lcbd_{scale_km}km", driver="GPKG", engine="pyogrio")
        registry.add(gpkg, "12", _label("grid_lcbd_desc").format(scale=scale_km))

    summary = pd.DataFrame(summaries).sort_values("scale_km", ascending=False).reset_index(drop=True)
    richness_table = pd.concat(richness_all, ignore_index=True) if richness_all else pd.DataFrame()
    occupancy_table = pd.concat(occupancy_all, ignore_index=True) if occupancy_all else pd.DataFrame()
    effort_table = pd.concat(effort_all, ignore_index=True) if effort_all else pd.DataFrame()
    lcbd_table_all = pd.concat(lcbd_all, ignore_index=True) if lcbd_all else pd.DataFrame()
    decay_table = pd.concat(distance_decay_all, ignore_index=True) if distance_decay_all else pd.DataFrame()
    assignment_qa = pd.DataFrame(assignment_qa_rows).sort_values("scale_km").reset_index(drop=True)

    canonical, hierarchy_relations, canonical_scale = _build_canonical_persistence(scale_results, official_grids)
    selected_result = scale_results.get(int(selected_grid_km), {})
    selected_grid_with_records = selected_result.get("grid_with_records", gpd.GeoDataFrame())
    if selected_grid_with_records is None or selected_grid_with_records.empty:
        selected_grid = official_grids.get(int(selected_grid_km), official_marine_cells)
        selected_grid_with_records = selected_grid.copy()
    selected_persistence = _aggregate_persistence_to_selected(
        canonical, canonical_scale, int(selected_grid_km), selected_grid_with_records, official_grids
    )

    # Selected-scale LCBD, richness, and abundance are retained for figures and downstream summaries.
    selected_lcbd = _scale_cell_lookup(scale_results, int(selected_grid_km)).reset_index()
    if not selected_lcbd.empty:
        selected_lcbd = selected_lcbd.rename(columns={"grid_id_scale": "master_id"})
        selected_persistence = selected_persistence.drop(
            columns=[c for c in ("LCBD", "LCBD_p_value", "LCBD_p_adjust_BH", "hotspot", "hotspot_significant_fdr") if c in selected_persistence],
            errors="ignore",
        ).merge(
            selected_lcbd[[c for c in ("master_id", "LCBD", "LCBD_p_value", "LCBD_p_adjust_BH", "hotspot", "hotspot_significant_fdr") if c in selected_lcbd]],
            on="master_id", how="left", validate="one_to_one",
        )
    selected_persistence["LCBD_selected"] = pd.to_numeric(selected_persistence.get("LCBD"), errors="coerce")
    selected_persistence["LCBD_p_value_selected"] = pd.to_numeric(selected_persistence.get("LCBD_p_value"), errors="coerce")
    selected_persistence["hotspot_lcbd"] = selected_persistence.get("hotspot_significant_fdr", pd.Series(False, index=selected_persistence.index)).astype("boolean").fillna(False).astype(bool)
    selected_persistence["richness"] = pd.to_numeric(selected_persistence.get("richness"), errors="coerce")
    selected_persistence["abundance"] = pd.to_numeric(selected_persistence.get("abundance"), errors="coerce")

    adjacency = _polygon_adjacency(selected_persistence)
    moran = moran_i(selected_persistence.get("hotspot_persistence", pd.Series(dtype=float)), adjacency, settings.permutations, settings.random_seed + 150)
    moran_permutations = _moran_null_distribution(selected_persistence.get("hotspot_persistence", pd.Series(dtype=float)), adjacency, settings.permutations, settings.random_seed + 150)

    hot = selected_persistence[selected_persistence.get("is_hotspot_any_scale", False)].copy()
    if len(hot) >= 2:
        coordinates = np.column_stack([hot.geometry.centroid.x, hot.geometry.centroid.y])
        labels = DBSCAN(eps=15_000, min_samples=2).fit_predict(coordinates)
        hot["hotspot_cluster"] = np.where(labels >= 0, labels + 1, 0)
    else:
        hot["hotspot_cluster"] = 0
    selected_persistence = selected_persistence.merge(hot[["master_id", "hotspot_cluster"]], on="master_id", how="left")
    selected_persistence["hotspot_cluster"] = pd.to_numeric(selected_persistence["hotspot_cluster"], errors="coerce").fillna(0).astype(int)
    selected_persistence["hotspot_cluster_method"] = "DBSCAN fixed-radius 15 km descriptive core; not management-zone continuity"
    stability = pd.DataFrame(selected_persistence.drop(columns="geometry", errors="ignore")).copy()
    cluster_summary = (
        selected_persistence[selected_persistence["hotspot_cluster"].gt(0)]
        .groupby("hotspot_cluster", observed=True)
        .agg(
            n_cells=("master_id", "size"),
            persistence_mean=("hotspot_persistence", "mean"),
            persistence_max=("hotspot_persistence", "max"),
            richness_mean=("richness", "mean"),
            LCBD_mean=("LCBD_selected", "mean"),
        ).reset_index()
    )

    official_master, spatial_qa = _build_official_conservation_master(
        official_marine_cells, community, selected_persistence, int(selected_grid_km), settings.min_records_cell
    )
    hierarchy_coverage_rows = []
    if canonical_scale is not None:
        canonical_n = len(canonical)
        for scale in REQUESTED_SCALES:
            if scale < canonical_scale or scale not in official_grids:
                hierarchy_coverage_rows.append({"check": f"official_hierarchy_{canonical_scale}_to_{scale}km", "status": "WARN", "detail": "scale unavailable/not applicable"})
                continue
            if scale == canonical_scale:
                mapped = canonical_n
            else:
                rel = hierarchy_relations[hierarchy_relations["to_scale_km"].eq(scale)] if not hierarchy_relations.empty else pd.DataFrame()
                mapped = rel["fine_grid_id"].nunique() if not rel.empty else 0
            hierarchy_coverage_rows.append({"check": f"official_hierarchy_{canonical_scale}_to_{scale}km", "status": "PASS" if mapped == canonical_n else "WARN", "detail": f"{mapped}/{canonical_n}"})
    spatial_qa = pd.concat([spatial_qa, pd.DataFrame(hierarchy_coverage_rows)], ignore_index=True)

    master_path = directories["02_intermedios"] / _label("master_gpkg")
    translate_geodataframe(selected_persistence).to_file(master_path, layer="hotspots_malla_maestra", driver="GPKG", engine="pyogrio")
    registry.add(master_path, "12", _label("master_desc").format(scale=selected_grid_km))
    official_path = directories["02_intermedios"] / _label("conservation_gpkg")
    translate_geodataframe(official_master).to_file(official_path, layer="malla_maestra_oficial_conservacion", driver="GPKG", engine="pyogrio")
    registry.add(official_path, "12/21", _label("conservation_desc"))

    assignment_path = csv2(assignment_qa, directories["07_debug"] / _label("assignment_qa_csv"))
    hierarchy_path = csv2(hierarchy_relations, directories["07_debug"] / _label("hierarchy_csv"))
    canonical_path = csv2(pd.DataFrame(canonical.drop(columns="geometry", errors="ignore")), directories["07_debug"] / _label("canonical_csv"))
    spatial_qa_path = csv2(spatial_qa, directories["07_debug"] / _label("spatial_qa_csv"))
    registry.add(assignment_path, "QA", _label("assignment_qa_desc"))
    registry.add(hierarchy_path, "QA", _label("hierarchy_desc"))
    registry.add(canonical_path, "QA", _label("canonical_desc"))
    registry.add(spatial_qa_path, "QA", _label("spatial_qa_desc"))

    tables = {
        "Resumen_multiscale": summary,
        "Riqueza_multiscale": richness_table,
        "Ocupacion_multiscale": occupancy_table,
        "Esfuerzo_multiscale": effort_table,
        "LCBD_multiscale": lcbd_table_all,
        "Distance_decay_multiscale": decay_table,
        "Asignacion_oficial_por_escala": assignment_qa,
        "Jerarquia_oficial_MITECO": hierarchy_relations,
        "Persistencia_canonica": pd.DataFrame(canonical.drop(columns="geometry", errors="ignore")),
        "Persistencia_hotspots": pd.DataFrame(selected_persistence.drop(columns="geometry", errors="ignore")),
        "Moran_persistencia": pd.DataFrame([moran]),
        "Moran_permutaciones": moran_permutations,
        "Estabilidad_hotspots": stability,
        "Clusters_hotspots": cluster_summary,
    }
    book = excel_book(tables, table_dir / _label("workbook"))
    registry.add(book, "12", _label("workbook_desc"))
    for name, frame in tables.items():
        path = csv2(frame, table_dir / f"Table_12_{name}.csv")
        registry.add(path, "12", f"{_label('table_prefix')} {name.replace('_', ' ')}")

    moran_text = text_file(
        _label("moran_text").format(I=moran.get("Moran_I", np.nan), expected=moran.get("expected_I", np.nan), p=moran.get("p_value", np.nan), permutations=settings.permutations),
        model_dir / _label("moran_txt"),
    )
    registry.add(moran_text, "12", _label("moran_desc"))

    note = _label("method_note").format(
        scales=", ".join(map(str, REQUESTED_SCALES)),
        min_events=settings.min_records_cell,
        canonical=(canonical_scale if canonical_scale is not None else "NA"),
        selected=selected_grid_km,
        moran=moran.get("Moran_I", np.nan),
        p=moran.get("p_value", np.nan),
    )
    note_path = text_file(note, model_dir / _label("method_note_file"))
    registry.add(note_path, "12", _label("method_note_desc"))

    if not summary.empty:
        fig, ax = plt.subplots(figsize=(8, 5.5))
        plot_summary = summary[summary["analysis_status"].eq("estimable")].copy()
        if not plot_summary.empty:
            sns.lineplot(data=plot_summary.sort_values("scale_km"), x="scale_km", y="mean_richness", marker="o", ax=ax, color="#2a9d8f")
            ax.invert_xaxis()
        ax.set(title=_label("richness_title"), xlabel=_label("scale_xlabel"), ylabel=_label("richness_ylabel"))
        for path in save_figure(fig, figure_dir / "Figure_12_Multiscale_Richness"):
            registry.add(path, "12", _label("richness_fig_desc"))

        fig, ax = plt.subplots(figsize=(8, 5.5))
        if not plot_summary.empty:
            sns.barplot(data=plot_summary, x="scale_km", y="n_hotspots_significant", color="#e76f51", ax=ax)
        ax.set(title=_label("hotspots_title"), xlabel=_label("scale_xlabel"), ylabel=_label("hotspots_ylabel"))
        for path in save_figure(fig, figure_dir / "Figure_12_Hotspots_by_Scale"):
            registry.add(path, "12", _label("hotspots_fig_desc"))

    fig = persistence_hotspot_figure(selected_persistence, cartographic_context)
    for path in save_figure(fig, figure_dir / "Figure_12_Hotspot_Persistence"):
        registry.add(path, "12", _label("persistence_fig_desc"))
    fig, ax = plt.subplots(figsize=(8, 5.5))
    if not moran_permutations.empty:
        sns.histplot(moran_permutations, x="Moran_I", bins=30, color="#6baed6", ax=ax)
        ax.axvline(moran.get("Moran_I", np.nan), color="#b2182b", linewidth=2, label=_label("observed"))
        ax.legend()
    ax.set(title=_label("moran_title"), xlabel="Moran I")
    for path in save_figure(fig, figure_dir / "Figure_Moran_MC_High_Significant_Hotspot_Histogram"):
        registry.add(path, "12", _label("moran_fig_desc"))

    hotspot_columns = [f"hotspot_{scale}km" for scale in REQUESTED_SCALES]
    return {
        "scale_results": scale_results,
        "summary": summary,
        "master_hotspots": official_master,
        "canonical_master_hotspots": canonical,
        "selected_persistence_grid": selected_persistence,
        "official_hierarchy_relations": hierarchy_relations,
        "assignment_qa": assignment_qa,
        "spatial_qa": spatial_qa,
        "moran": moran,
        "hotspot_columns": hotspot_columns,
        "master_scale_km": int(selected_grid_km),
        "canonical_support_scale_km": canonical_scale,
        "multiscale_method": "official_MITECO_event_supported_Jaccard_Mantel",
    }
