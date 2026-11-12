"""Assignment of observations to cells and visual clipping of land."""

from __future__ import annotations

from pathlib import Path
import hashlib
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from typing import Callable
from pyproj import Transformer
from shapely import clip_by_rect, make_valid, union_all
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon


def _missing_region_mask(series: pd.Series) -> pd.Series:
    values = series.astype("string").str.strip().str.casefold()
    return series.isna() | values.isin(
        {"", "nan", "none", "no data", "sin datos", "sin_datos", "no region"}
    )


def region_assignment_control(assigned: gpd.GeoDataFrame) -> pd.DataFrame:
    """Summarise how every assigned observation received its region."""

    definitions = {
        "direct_point_intersection": "The point intersected a MITECO subdivision polygon.",
        "reference_grid_10km": "The point did not intersect a subdivision directly; region was fixed from the official 10-km MITECO reference grid, independently of analytical resolution.",
        "unresolved": "No canonical MITECO region was available.",
    }
    if assigned.empty or "region_assignment_method" not in assigned:
        counts = pd.Series(dtype=int)
    else:
        counts = assigned["region_assignment_method"].value_counts(dropna=False)
    total = max(len(assigned), 1)
    rows = []
    for method, definition in definitions.items():
        count = int(counts.get(method, 0))
        rows.append(
            {
                "region_assignment_method": method,
                "n_observations": count,
                "pct_observations": 100 * count / total if len(assigned) else 0.0,
                "definition": definition,
            }
        )
    if "region_cell_disagreement" in assigned:
        disagreements = int(assigned["region_cell_disagreement"].fillna(False).sum())
        rows.append(
            {
                "region_assignment_method": "direct_cell_disagreement",
                "n_observations": disagreements,
                "pct_observations": 100 * disagreements / total if len(assigned) else 0.0,
                "definition": "Direct polygon region and official cell region differ; direct assignment is retained and flagged.",
            }
        )
    return pd.DataFrame(rows)


def assign_regions_from_reference_grid(
    points: gpd.GeoDataFrame,
    reference_grid: gpd.GeoDataFrame,
    tolerance_m: float,
) -> pd.DataFrame:
    """Assign a canonical region from the official MITECO reference grid.

    This function is used only for observations without a direct intersection
    with a MITECO subdivision. Region is assigned first by intersection with an
    official cell and, only when no intersection exists, from the nearest
    official cell within ``tolerance_m``. Marine areas, GSHHS and the analytical
    resolution selected by the user do not participate in this step.
    """
    columns = [
        "obs_id",
        "Region_slug_reference",
        "Region_MITECO_reference",
        "reference_grid_id",
        "reference_region_method",
        "reference_region_distance_m",
    ]
    if points.empty:
        return pd.DataFrame(columns=columns)
    needed = {"grid_id", "grid_order", "Region_slug", "Region_MITECO", "geometry"}
    missing = needed.difference(reference_grid.columns)
    if missing:
        raise ValueError(
            "The MITECO reference grid does not contain the required columns: "
            + ", ".join(sorted(missing))
        )

    grid = reference_grid[["grid_id", "grid_order", "Region_slug", "Region_MITECO", "geometry"]].copy()
    grid = grid.rename(
        columns={
            "grid_id": "reference_grid_id",
            "Region_slug": "Region_slug_reference",
            "Region_MITECO": "Region_MITECO_reference",
        }
    )
    hits = gpd.sjoin(points[["obs_id", "geometry"]], grid, how="left", predicate="intersects")
    hits = hits.sort_values(["obs_id", "grid_order", "reference_grid_id"], na_position="last")
    direct = hits[hits["reference_grid_id"].notna()].drop_duplicates("obs_id", keep="first").copy()
    direct["reference_region_method"] = "reference_grid_10km_intersects"
    direct["reference_region_distance_m"] = 0.0

    unmatched_ids = set(points["obs_id"]) - set(direct["obs_id"])
    nearest = pd.DataFrame(columns=direct.columns)
    if unmatched_ids:
        unmatched = points[points["obs_id"].isin(unmatched_ids)][["obs_id", "geometry"]].copy()
        nearest = gpd.sjoin_nearest(
            unmatched,
            grid,
            how="left",
            max_distance=float(tolerance_m),
            distance_col="reference_region_distance_m",
        )
        nearest = nearest.sort_values(
            ["obs_id", "reference_region_distance_m", "grid_order", "reference_grid_id"],
            na_position="last",
        )
        nearest = nearest[nearest["reference_grid_id"].notna()].drop_duplicates("obs_id", keep="first")
        nearest["reference_region_method"] = "reference_grid_10km_nearest"

    frames = [frame for frame in (direct, nearest) if not frame.empty]
    matched = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)
    if matched.empty:
        return pd.DataFrame(columns=columns)
    return matched[columns].sort_values("obs_id").reset_index(drop=True)


def assign_points_to_grid(
    points: gpd.GeoDataFrame,
    grid: gpd.GeoDataFrame,
    tolerance_m: float,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, dict[str, int]]:
    # A cell with no validated positive marine surface cannot receive an
    # analytical observation. It remains in the loaded grid for audit, but
    # allowing a direct intersection with it would create an assignment that
    # is incompatible with the density denominator. Points falling in those
    # cells therefore pass to the nearest-cell mechanism, which only considers
    # cells with positive marine surface and respects the configured tolerance.
    if "Area_mar_km2" not in grid.columns:
        raise ValueError(
            "The grid does not contain Area_mar_km2 before observation assignment."
        )
    marine_area = pd.to_numeric(grid["Area_mar_km2"], errors="coerce")
    valid_marine_cell = marine_area.notna() & marine_area.gt(0)
    grid_for_assignment = grid.loc[valid_marine_cell].copy()
    if grid_for_assignment.empty:
        raise ValueError(
            "No cells with validated positive marine surface are available for observation assignment."
        )

    grid_columns = [
        "grid_id",
        "official_cell_code",
        "Area_mar_km2",
        "grid_order",
        "geometry",
    ]
    if "official_marine_flag" in grid.columns:
        grid_columns.append("official_marine_flag")
    for column in (
        "Area_mar_oficial_km2",
        "Area_mar_gshhs_km2",
        "Area_mar_miteco_fallback_km2",
        "Area_celda_km2",
        "Area_mar_source",
    ):
        if column in grid.columns:
            grid_columns.append(column)
    if "Region_slug" in grid.columns:
        grid_columns.append("Region_slug")
    if "Region_MITECO" in grid.columns:
        grid_columns.append("Region_MITECO")
    grid_join = grid_for_assignment[grid_columns].rename(
        columns={
            "Region_slug": "Region_slug_cell",
            "Region_MITECO": "Region_MITECO_cell",
        }
    )
    hits = gpd.sjoin(points, grid_join, how="left", predicate="intersects")
    fallback_hit = hits.get("Area_mar_source", pd.Series("", index=hits.index)).astype("string").eq(
        "miteco_demarcation_fallback_geometry"
    )
    point_region = hits.get("Region_slug", pd.Series(pd.NA, index=hits.index)).astype("string").str.strip().str.casefold()
    cell_region = hits.get("Region_slug_cell", pd.Series(pd.NA, index=hits.index)).astype("string").str.strip().str.casefold()
    point_region_valid = ~point_region.isin({"", "nan", "none", "no data", "sin datos", "sin_datos", "no region", "<na>"})
    fallback_direct_ok = point_region_valid & point_region.eq(cell_region)
    hits = hits.loc[(~fallback_hit) | fallback_direct_ok].copy()
    hits = hits.sort_values(["obs_id", "grid_order"], na_position="last")
    direct = (
        hits[hits["grid_id"].notna()].drop_duplicates("obs_id", keep="first").copy()
    )
    direct["dist_to_cell_m"] = 0.0
    direct["assignment_method"] = np.where(
        direct.get("Area_mar_source", pd.Series("", index=direct.index)).astype("string").eq(
            "miteco_demarcation_fallback_geometry"
        ),
        "intersects_miteco_fallback",
        "intersects",
    )

    unmatched_ids = set(points["obs_id"]) - set(direct["obs_id"])
    nearest = gpd.GeoDataFrame(
        columns=direct.columns, geometry="geometry", crs=points.crs
    )
    if unmatched_ids:
        unmatched = points[points["obs_id"].isin(unmatched_ids)].copy()
        nearest_grid_join = grid_join.loc[
            ~grid_join.get("Area_mar_source", pd.Series("", index=grid_join.index)).astype("string").eq(
                "miteco_demarcation_fallback_geometry"
            )
        ].copy()
        nearest = gpd.sjoin_nearest(
            unmatched,
            nearest_grid_join,
            how="left",
            max_distance=tolerance_m,
            distance_col="dist_to_cell_m",
        )
        nearest = nearest.sort_values(
            ["obs_id", "dist_to_cell_m", "grid_order"], na_position="last"
        )
        nearest = nearest[nearest["grid_id"].notna()].drop_duplicates(
            "obs_id", keep="first"
        )
        nearest["assignment_method"] = "nearest"

    frames = [frame for frame in (direct, nearest) if not frame.empty]
    combined = pd.concat(frames, ignore_index=True) if frames else direct.copy()
    assigned = gpd.GeoDataFrame(combined, crs=points.crs)
    assigned = assigned.sort_values("obs_id").reset_index(drop=True)
    for column in ("Region_slug", "Region_MITECO"):
        if column not in assigned.columns:
            assigned[column] = pd.NA
    for column in ("Region_slug_cell", "Region_MITECO_cell"):
        if column not in assigned.columns:
            assigned[column] = pd.NA
    if "official_marine_flag" not in assigned.columns:
        assigned["official_marine_flag"] = True
    assigned["Region_slug_direct"] = assigned["Region_slug"]
    assigned["Region_MITECO_direct"] = assigned["Region_MITECO"]
    missing_slug = _missing_region_mask(assigned["Region_slug"])
    assigned["region_cell_disagreement"] = (
        ~missing_slug
        & ~_missing_region_mask(assigned["Region_slug_cell"])
        & assigned["Region_slug"].astype("string").str.casefold().ne(
            assigned["Region_slug_cell"].astype("string").str.casefold()
        )
    )
    # Regional membership is never inferred from the selected analytical cell.
    # Missing direct regions remain unresolved here and are resolved, when possible,
    # by the canonical official MITECO 10-km reference step in the main pipeline.
    assigned["region_assignment_method"] = np.where(
        ~missing_slug, "direct_point_intersection", "unresolved"
    )
    unassigned = points[~points["obs_id"].isin(assigned["obs_id"])].copy()
    stats = {
        "grid_cells_total": int(len(grid)),
        "grid_cells_valid_marine": int(valid_marine_cell.sum()),
        "grid_cells_excluded_no_marine_surface": int((~valid_marine_cell).sum()),
        "points_total": int(len(points)),
        "points_direct": int(assigned["assignment_method"].astype("string").str.startswith("intersects").sum()),
        "points_direct_miteco_fallback": int((assigned["assignment_method"] == "intersects_miteco_fallback").sum()),
        "points_nearest": int((assigned["assignment_method"] == "nearest").sum()),
        "points_unassigned": int(len(unassigned)),
        "points_region_direct": int(
            (assigned["region_assignment_method"] == "direct_point_intersection").sum()
        ),
        "points_region_unresolved": int(
            (assigned["region_assignment_method"] == "unresolved").sum()
        ),
        "points_region_cell_disagreement": int(
            assigned["region_cell_disagreement"].fillna(False).sum()
        ),
    }
    return assigned, unassigned, stats



def official_grid_relation(
    fine_grid: gpd.GeoDataFrame,
    coarse_grid: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Relate fine official MITECO cells to their containing official coarse cell.

    The primary rule uses a representative point guaranteed to lie inside the
    fine geometry. Border cases fall back to maximum geometric overlap and then
    the stable coarse-cell identifier. No ecological variable is used to choose
    a correspondence.
    """

    columns = [
        "fine_grid_id",
        "coarse_grid_id",
        "mapping_method",
        "overlap_area_km2",
        "overlap_pct_fine_geometry",
    ]
    if fine_grid is None or coarse_grid is None or fine_grid.empty or coarse_grid.empty:
        return pd.DataFrame(columns=columns)
    if fine_grid.crs is None or coarse_grid.crs is None:
        raise ValueError("Official multiscale grids must have a defined CRS.")
    if "grid_id" not in fine_grid or "grid_id" not in coarse_grid:
        raise ValueError("Official multiscale grids must contain grid_id.")

    fine = fine_grid[[c for c in ("grid_id", "Region_slug", "geometry") if c in fine_grid.columns]].copy()
    coarse = coarse_grid[[c for c in ("grid_id", "Region_slug", "geometry") if c in coarse_grid.columns]].copy()
    fine = gpd.GeoDataFrame(fine, geometry="geometry", crs=fine_grid.crs)
    coarse = gpd.GeoDataFrame(coarse, geometry="geometry", crs=coarse_grid.crs).to_crs(fine.crs)
    fine["grid_id"] = fine["grid_id"].astype(str)
    coarse["grid_id"] = coarse["grid_id"].astype(str)
    fine = fine.drop_duplicates("grid_id").reset_index(drop=True)
    coarse = coarse.drop_duplicates("grid_id").reset_index(drop=True)

    fine_points = fine.rename(columns={"grid_id": "fine_grid_id"})
    fine_points = gpd.GeoDataFrame(fine_points, geometry="geometry", crs=fine.crs)
    fine_points.geometry = fine_points.geometry.representative_point()
    coarse_join = coarse.rename(columns={"grid_id": "coarse_grid_id"})
    if "Region_slug" in fine_points.columns:
        fine_points = fine_points.rename(columns={"Region_slug": "fine_region_slug"})
    if "Region_slug" in coarse_join.columns:
        coarse_join = coarse_join.rename(columns={"Region_slug": "coarse_region_slug"})

    direct = gpd.sjoin(fine_points, coarse_join, how="left", predicate="within").drop(
        columns="index_right", errors="ignore"
    )
    direct = direct[direct["coarse_grid_id"].notna()].copy()
    if {"fine_region_slug", "coarse_region_slug"}.issubset(direct.columns):
        same_region = direct["fine_region_slug"].isna() | direct["coarse_region_slug"].isna() | (
            direct["fine_region_slug"].astype("string").str.casefold()
            == direct["coarse_region_slug"].astype("string").str.casefold()
        )
        direct = direct[same_region].copy()
    direct = direct.sort_values(["fine_grid_id", "coarse_grid_id"]).drop_duplicates(
        "fine_grid_id", keep="first"
    )
    direct["mapping_method"] = "representative_point_within"

    matched = set(direct["fine_grid_id"].astype(str))
    unmatched = fine[~fine["grid_id"].isin(matched)].copy()
    fallback_rows: list[dict[str, object]] = []
    if not unmatched.empty:
        coarse_geom = coarse.set_index("grid_id").geometry.to_dict()
        coarse_region = coarse.set_index("grid_id").get("Region_slug", pd.Series(dtype="object")).to_dict() if "Region_slug" in coarse.columns else {}
        coarse_index = coarse.sindex
        for row in unmatched.itertuples():
            fine_id = str(row.grid_id)
            geom = row.geometry
            candidates = list(coarse_index.query(geom, predicate="intersects"))
            scored: list[tuple[float, str]] = []
            fine_region = getattr(row, "Region_slug", None)
            for idx in candidates:
                coarse_id = str(coarse.iloc[idx]["grid_id"])
                if fine_region is not None and coarse_region:
                    candidate_region = coarse_region.get(coarse_id)
                    if pd.notna(fine_region) and pd.notna(candidate_region) and str(fine_region).casefold() != str(candidate_region).casefold():
                        continue
                target = coarse_geom[coarse_id]
                area = float(geom.intersection(target).area)
                if area > 0:
                    scored.append((area, coarse_id))
            if scored:
                scored.sort(key=lambda item: (-item[0], item[1]))
                area, coarse_id = scored[0]
                fallback_rows.append(
                    {
                        "fine_grid_id": fine_id,
                        "coarse_grid_id": coarse_id,
                        "mapping_method": "maximum_geometric_overlap_fallback",
                        "overlap_area_km2": area / 1_000_000,
                        "overlap_pct_fine_geometry": 100 * area / float(geom.area) if geom.area > 0 else np.nan,
                    }
                )

    direct_rows = direct[["fine_grid_id", "coarse_grid_id", "mapping_method"]].copy()
    fine_geom = fine.set_index("grid_id").geometry.to_dict()
    coarse_geom = coarse.set_index("grid_id").geometry.to_dict()
    overlap_area = []
    overlap_pct = []
    for row in direct_rows.itertuples():
        source = fine_geom[str(row.fine_grid_id)]
        target = coarse_geom[str(row.coarse_grid_id)]
        area = float(source.intersection(target).area)
        overlap_area.append(area / 1_000_000)
        overlap_pct.append(100 * area / float(source.area) if source.area > 0 else np.nan)
    direct_rows["overlap_area_km2"] = overlap_area
    direct_rows["overlap_pct_fine_geometry"] = overlap_pct

    relation = pd.concat([direct_rows, pd.DataFrame(fallback_rows)], ignore_index=True)
    if relation.empty:
        return pd.DataFrame(columns=columns)
    relation["fine_grid_id"] = relation["fine_grid_id"].astype(str)
    relation["coarse_grid_id"] = relation["coarse_grid_id"].astype(str)
    return relation[columns].sort_values("fine_grid_id").reset_index(drop=True)


def build_assignment_spatial_audit(
    points: gpd.GeoDataFrame,
    grid: gpd.GeoDataFrame,
    assigned: gpd.GeoDataFrame,
    tolerance_m: float,
    gshhg_path: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Audit ``nearest`` assignments and unassigned points without modifying them."""
    if points.empty:
        empty = pd.DataFrame()
        return empty, empty, grid.iloc[0:0].copy(), gpd.GeoDataFrame(geometry=[], crs=grid.crs)

    assigned_base = pd.DataFrame(assigned.drop(columns="geometry", errors="ignore")).copy()
    method_series = assigned_base.get("assignment_method", pd.Series(index=assigned_base.index, dtype="string"))
    nearest_ids = set(assigned_base.loc[method_series.eq("nearest"), "obs_id"].tolist())
    assigned_ids = set(assigned_base.get("obs_id", pd.Series(dtype=object)).tolist())
    unassigned_ids = set(points["obs_id"].tolist()) - assigned_ids
    issue_ids = nearest_ids | unassigned_ids
    if not issue_ids:
        summary = pd.DataFrame([{"estado_asignacion": "no_issues", "causa_diagnostica": "None", "n_observaciones": 0}])
        return pd.DataFrame(), summary, grid.iloc[0:0].copy(), gpd.GeoDataFrame(geometry=[], crs=grid.crs)

    issue_points = points.loc[points["obs_id"].isin(issue_ids)].copy()
    issue_points_wgs = issue_points.to_crs(4326)

    grid_cols = [c for c in (
        "grid_id", "official_cell_code", "grid_order", "Area_mar_km2",
        "Area_mar_oficial_km2", "Area_mar_gshhs_km2", "Area_celda_km2",
        "Area_mar_source", "Region_slug", "Region_MITECO", "geometry",
    ) if c in grid.columns]
    grid_all = grid[grid_cols].copy()
    if "grid_order" not in grid_all.columns:
        grid_all["grid_order"] = np.arange(len(grid_all), dtype=int)

    original = gpd.sjoin(issue_points[["obs_id", "geometry"]], grid_all, how="left", predicate="intersects")
    original = original.sort_values(["obs_id", "grid_order"], na_position="last").drop_duplicates("obs_id", keep="first")
    original = pd.DataFrame(original.drop(columns="geometry", errors="ignore")).rename(columns={
        "grid_id": "celda_miteco_original", "official_cell_code": "codigo_celda_original",
        "Area_mar_km2": "area_mar_original_km2", "Area_mar_oficial_km2": "area_mar_oficial_original_km2",
        "Area_mar_gshhs_km2": "area_mar_gshhs_original_km2", "Area_celda_km2": "area_celda_original_km2",
        "Area_mar_source": "fuente_area_original", "Region_slug": "region_slug_celda_original",
        "Region_MITECO": "region_miteco_celda_original",
    })
    original = original[[c for c in original.columns if c not in {"index_right", "grid_order"}]]

    marine_area = pd.to_numeric(grid["Area_mar_km2"], errors="coerce")
    valid_grid = grid.loc[marine_area.notna() & marine_area.gt(0), grid_cols].copy()
    if valid_grid.empty:
        nearest_any = pd.DataFrame({"obs_id": issue_points["obs_id"].to_numpy()})
    else:
        nearest_any = gpd.sjoin_nearest(issue_points[["obs_id", "geometry"]], valid_grid, how="left", distance_col="distancia_celda_marina_mas_proxima_m")
        nearest_any = nearest_any.sort_values(["obs_id", "distancia_celda_marina_mas_proxima_m", "grid_order"], na_position="last").drop_duplicates("obs_id", keep="first")
        nearest_any = pd.DataFrame(nearest_any.drop(columns="geometry", errors="ignore")).rename(columns={
            "grid_id": "celda_marina_valida_mas_proxima", "official_cell_code": "codigo_celda_marina_mas_proxima",
            "Area_mar_km2": "area_mar_celda_mas_proxima_km2",
        })
        nearest_keep = [
            "obs_id", "celda_marina_valida_mas_proxima",
            "codigo_celda_marina_mas_proxima", "area_mar_celda_mas_proxima_km2",
            "distancia_celda_marina_mas_proxima_m",
        ]
        nearest_any = nearest_any[[c for c in nearest_keep if c in nearest_any.columns]]

    land_flag = pd.DataFrame({"obs_id": issue_points["obs_id"].to_numpy(), "punto_sobre_tierra_gshhs": pd.NA})
    land_for_map = gpd.GeoDataFrame(geometry=[], crs=grid.crs)
    if gshhg_path is not None and not issue_points.empty:
        try:
            land = _load_gshhs_land(issue_points, Path(gshhg_path))
            if not land.empty:
                land_hits = gpd.sjoin(issue_points[["obs_id", "geometry"]], land[["geometry"]], how="left", predicate="intersects")
                on_land_ids = set(land_hits.loc[land_hits["index_right"].notna(), "obs_id"].tolist())
                land_flag["punto_sobre_tierra_gshhs"] = land_flag["obs_id"].isin(on_land_ids)
                buffers = issue_points.geometry.buffer(max(float(tolerance_m) * 1.5, 1500.0))
                mask_geom = union_all([geom for geom in buffers if geom is not None and not geom.is_empty])
                if mask_geom is not None and not mask_geom.is_empty:
                    clipped = land.geometry.intersection(mask_geom)
                    clipped = clipped[(~clipped.isna()) & (~clipped.is_empty)]
                    if len(clipped):
                        land_for_map = gpd.GeoDataFrame(geometry=clipped.map(make_valid), crs=grid.crs)
                        land_for_map.geometry = land_for_map.geometry.simplify(10.0, preserve_topology=True)
        except Exception:
            pass

    assigned_info = assigned_base[[c for c in ("obs_id", "grid_id", "official_cell_code", "Area_mar_km2", "assignment_method", "dist_to_cell_m") if c in assigned_base.columns]].copy()
    assigned_info = assigned_info.rename(columns={
        "grid_id": "celda_asignada", "official_cell_code": "codigo_celda_asignada", "Area_mar_km2": "area_mar_celda_asignada_km2",
        "assignment_method": "metodo_asignacion", "dist_to_cell_m": "distancia_asignacion_m",
    })

    audit = pd.DataFrame(issue_points.drop(columns="geometry", errors="ignore")).copy()
    audit["longitud_wgs84"] = issue_points_wgs.geometry.x.to_numpy()
    audit["latitud_wgs84"] = issue_points_wgs.geometry.y.to_numpy()
    audit = audit.merge(assigned_info, on="obs_id", how="left").merge(original, on="obs_id", how="left").merge(nearest_any, on="obs_id", how="left").merge(land_flag, on="obs_id", how="left")
    audit["estado_asignacion"] = np.where(audit["obs_id"].isin(nearest_ids), "nearest", "no_asignado")
    audit["tolerancia_m"] = float(tolerance_m)
    nearest_dist = pd.to_numeric(audit.get("distancia_celda_marina_mas_proxima_m"), errors="coerce")
    audit["celda_marina_mas_proxima_dentro_tolerancia"] = nearest_dist.le(float(tolerance_m))
    original_area = pd.to_numeric(audit.get("area_mar_original_km2"), errors="coerce")
    original_cell = audit.get("celda_miteco_original", pd.Series(index=audit.index, dtype="string"))
    original_exists = original_cell.notna()
    original_invalid = original_exists & (original_area.isna() | original_area.le(0))

    causes = []
    for idx, row in audit.iterrows():
        status = row.get("estado_asignacion")
        distance = nearest_dist.loc[idx]
        if status == "nearest":
            if bool(original_invalid.loc[idx]):
                cause = "MITECO_CELL_WITHOUT_MARINE_SURFACE_REASSIGNED"
            elif not bool(original_exists.loc[idx]):
                cause = "NO_MITECO_INTERSECTION_REASSIGNED_BY_PROXIMITY"
            else:
                cause = "PROXIMITY_REASSIGNMENT_OTHER_CAUSE"
        else:
            if bool(original_invalid.loc[idx]) and pd.notna(distance) and float(distance) > float(tolerance_m):
                cause = "MITECO_CELL_WITHOUT_MARINE_SURFACE_AND_VALID_CELL_BEYOND_TOLERANCE"
            elif not bool(original_exists.loc[idx]) and pd.notna(distance) and float(distance) > float(tolerance_m):
                cause = "NO_MITECO_INTERSECTION_AND_VALID_CELL_BEYOND_TOLERANCE"
            elif pd.isna(distance):
                cause = "NO_VALID_MARINE_CELL_LOCATABLE"
            else:
                cause = "UNASSIGNED_OTHER_CARTOGRAPHIC_CONFLICT"
        causes.append(cause)
    audit["causa_diagnostica"] = causes

    important = ["obs_id", "Id", "Species", "Source", "Fuente", "Platform", "Procedencia", "longitud_wgs84", "latitud_wgs84", "estado_asignacion", "metodo_asignacion", "celda_miteco_original", "area_mar_original_km2", "punto_sobre_tierra_gshhs", "celda_asignada", "distancia_asignacion_m", "celda_marina_valida_mas_proxima", "distancia_celda_marina_mas_proxima_m", "tolerancia_m", "celda_marina_mas_proxima_dentro_tolerancia", "causa_diagnostica"]
    ordered = [c for c in important if c in audit.columns]
    audit = audit[ordered + [c for c in audit.columns if c not in ordered]]
    summary = audit.groupby(["estado_asignacion", "causa_diagnostica", "punto_sobre_tierra_gshhs"], dropna=False).size().reset_index(name="n_observaciones")
    direct_count = int(method_series.eq("intersects").sum())
    if direct_count:
        summary = pd.concat([
            pd.DataFrame([{
                "estado_asignacion": "intersects",
                "causa_diagnostica": "DIRECT_ASSIGNMENT_TO_VALID_MARINE_CELL",
                "punto_sobre_tierra_gshhs": pd.NA,
                "n_observaciones": direct_count,
            }]),
            summary,
        ], ignore_index=True)
    summary = summary.sort_values(["estado_asignacion", "n_observaciones"], ascending=[True, False]).reset_index(drop=True)

    issue_cell_ids = set(audit.get("celda_miteco_original", pd.Series(dtype="string")).dropna().astype(str))
    issue_cell_ids.update(audit.get("celda_marina_valida_mas_proxima", pd.Series(dtype="string")).dropna().astype(str))
    issue_cell_ids.update(audit.get("celda_asignada", pd.Series(dtype="string")).dropna().astype(str))
    issue_cells = grid.loc[grid["grid_id"].astype(str).isin(issue_cell_ids)].copy()
    return audit, summary, issue_cells, land_for_map


def write_assignment_qc_map(
    destination: Path,
    points: gpd.GeoDataFrame,
    assigned: gpd.GeoDataFrame,
    audit: pd.DataFrame,
    issue_cells: gpd.GeoDataFrame,
    land: gpd.GeoDataFrame,
    *,
    title: str = "Hispa-Syng · Spatial assignment quality control",
) -> Path:
    """Write a self-contained Leaflet map to inspect spatial assignments."""
    from .maps import _leaflet_assets

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    assigned_plain = pd.DataFrame(assigned.drop(columns="geometry", errors="ignore"))
    method_map = assigned_plain.set_index("obs_id")["assignment_method"] if "assignment_method" in assigned_plain.columns else pd.Series(dtype="string")
    diagnostic_map = audit.set_index("obs_id")["causa_diagnostica"] if not audit.empty and "causa_diagnostica" in audit.columns else pd.Series(dtype="string")
    distance_map = audit.set_index("obs_id")["distancia_celda_marina_mas_proxima_m"] if not audit.empty and "distancia_celda_marina_mas_proxima_m" in audit.columns else pd.Series(dtype=float)
    pts = points.copy()
    pts["estado_asignacion"] = pts["obs_id"].map(method_map).fillna("no_asignado")
    pts["causa_diagnostica"] = pts["obs_id"].map(diagnostic_map)
    pts["distancia_celda_marina_mas_proxima_m"] = pts["obs_id"].map(distance_map)
    pts = pts.to_crs(4326)
    point_fields = [c for c in ("obs_id", "Id", "Species", "estado_asignacion", "causa_diagnostica", "distancia_celda_marina_mas_proxima_m") if c in pts.columns]
    points_geojson = json.loads(pts[point_fields + ["geometry"]].to_json(drop_id=True))

    cells = issue_cells.to_crs(4326) if not issue_cells.empty else issue_cells
    cell_fields = [c for c in ("grid_id", "official_cell_code", "Area_mar_km2", "Area_mar_gshhs_km2", "Area_celda_km2", "Region_MITECO") if c in cells.columns]
    cells_geojson = json.loads(cells[cell_fields + ["geometry"]].to_json(drop_id=True)) if not cells.empty else {"type": "FeatureCollection", "features": []}
    land_wgs = land.to_crs(4326) if land is not None and not land.empty else land
    land_geojson = json.loads(land_wgs[["geometry"]].to_json(drop_id=True)) if land_wgs is not None and not land_wgs.empty else {"type": "FeatureCollection", "features": []}
    leaflet_css, leaflet_js = _leaflet_assets()
    html_text = f"""<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{title}</title><style>{leaflet_css}</style><style>
html,body,#map{{height:100%;margin:0}} .qc-title{{position:absolute;z-index:1000;top:10px;left:55px;background:#fff;padding:8px 12px;border-radius:5px;box-shadow:0 1px 5px #777;font:600 14px Arial;max-width:70vw}} .legend{{background:#fff;padding:8px 10px;line-height:1.55;font:12px Arial;box-shadow:0 1px 5px #777}} .dot{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}}</style></head><body><div class='qc-title'>{title}</div><div id='map'></div><script>{leaflet_js}</script><script>
const pointData={json.dumps(points_geojson, ensure_ascii=False, separators=(',',':'))};
const cellData={json.dumps(cells_geojson, ensure_ascii=False, separators=(',',':'))};
const landData={json.dumps(land_geojson, ensure_ascii=False, separators=(',',':'))};
const map=L.map('map',{{preferCanvas:true}});
const physical=L.tileLayer('https://{{s}}.tile.opentopomap.org/{{z}}/{{x}}/{{y}}.png',{{maxZoom:17,attribution:'Data: &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>, SRTM | Style: &copy; <a href="https://opentopomap.org" target="_blank">OpenTopoMap</a> (CC-BY-SA)'}});
const satellite=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',{{maxZoom:19,attribution:'Esri, Vantor, Earthstar Geographics, and the GIS User Community'}}).addTo(map);
const landLayer=L.geoJSON(landData,{{style:{{color:'#555',weight:1,fillColor:'#bdbdbd',fillOpacity:.22}}}}).addTo(map);
const cellLayer=L.geoJSON(cellData,{{style:f=>{{const a=Number(f.properties.Area_mar_km2);return {{color:(!Number.isFinite(a)||a<=0)?'#b2182b':'#2166ac',weight:2,fill:false,dashArray:'4 3'}}}},onEachFeature:(f,l)=>l.bindPopup(`<b>MITECO cell</b><br>${{f.properties.grid_id||''}}<br>Marine area: ${{f.properties.Area_mar_km2??'N.D.'}} km²`)}}).addTo(map);
function colorFor(s){{return s==='nearest'?'#f28e2b':(s==='no_asignado'?'#d62728':'#2ca02c')}}
const pointLayer=L.geoJSON(pointData,{{pointToLayer:(f,ll)=>L.circleMarker(ll,{{radius:f.properties.estado_asignacion==='intersects'?3.2:6,color:'#222',weight:.5,fillColor:colorFor(f.properties.estado_asignacion),fillOpacity:.9}}),onEachFeature:(f,l)=>{{const p=f.properties;const d=Number(p.distancia_celda_marina_mas_proxima_m);l.bindPopup(`<b>${{p.Species||'Observation'}}</b><br>obs_id: ${{p.obs_id}}<br>Status: ${{p.estado_asignacion}}<br>Cause: ${{p.causa_diagnostica||'—'}}<br>Distance to nearest valid marine cell: ${{Number.isFinite(d)?d.toFixed(1)+' m':'—'}}`);}}}}).addTo(map);
L.control.layers({{'Satellite':satellite,'Physical':physical}},{{'Observations':pointLayer,'Relevant cells':cellLayer,'GSHHS land around issues':landLayer}},{{collapsed:false}}).addTo(map);
const legend=L.control({{position:'bottomright'}});legend.onAdd=()=>{{const d=L.DomUtil.create('div','legend');d.innerHTML='<b>Assignment</b><br><span class=\"dot\" style=\"background:#2ca02c\"></span>Direct<br><span class=\"dot\" style=\"background:#f28e2b\"></span>Nearest<br><span class=\"dot\" style=\"background:#d62728\"></span>Unassigned';return d}};legend.addTo(map);
const b=pointLayer.getBounds();if(b.isValid())map.fitBounds(b.pad(.06));else map.setView([40,-4],6);
</script></body></html>"""
    destination.write_text(html_text, encoding="utf-8")
    return destination

def _polygonal_only(geometry):
    if geometry is None or geometry.is_empty:
        return None
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return geometry
    if isinstance(geometry, GeometryCollection):
        polygons = [
            part
            for part in geometry.geoms
            if isinstance(part, (Polygon, MultiPolygon)) and not part.is_empty
        ]
        return union_all(polygons) if polygons else None
    return None


def _bounds_in_crs(
    bounds: np.ndarray, from_crs: object, to_crs: object
) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = [float(value) for value in bounds]
    transformer = Transformer.from_crs(from_crs, to_crs, always_xy=True)
    corners = [
        transformer.transform(minx, miny),
        transformer.transform(minx, maxy),
        transformer.transform(maxx, miny),
        transformer.transform(maxx, maxy),
    ]
    xs, ys = zip(*corners)
    return min(xs), min(ys), max(xs), max(ys)


def _load_gshhs_land(
    frame: gpd.GeoDataFrame, gshhg_path: Path | None
) -> gpd.GeoDataFrame:
    if gshhg_path is None:
        raise FileNotFoundError(
            "GSHHS is required to remove land and calculate the actual marine surface used by every density."
        )
    gshhg_path = Path(gshhg_path)
    if not gshhg_path.is_file():
        raise FileNotFoundError(f"GSHHS shapefile was not found: {gshhg_path}")
    if frame.empty:
        raise ValueError("There are no geometries to which the GSHHS control can be applied.")
    if frame.crs is None:
        raise ValueError("The grid has no defined CRS before the GSHHS control.")

    info = pyogrio.read_info(gshhg_path)
    if not info.get("crs"):
        raise ValueError(f"GSHHS has no defined CRS: {gshhg_path}")
    bbox = _bounds_in_crs(frame.total_bounds, frame.crs, info["crs"])
    pad = 0.2
    bbox = (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad)
    land = gpd.read_file(gshhg_path, bbox=bbox, engine="pyogrio")
    if land.empty:
        return gpd.GeoDataFrame(geometry=[], crs=frame.crs)
    land = land.to_crs(frame.crs)
    # GDAL bbox filters source features but does not trim their complete
    # geometry. Clip returned GSHHS polygons once to the working-grid envelope
    # before repeated per-cell differences; geometry outside this envelope
    # cannot intersect any analysed cell.
    xmin, ymin, xmax, ymax = map(float, frame.total_bounds)

    def _clip_land_geometry(geometry):
        if geometry is None or geometry.is_empty:
            return geometry
        clipped = clip_by_rect(geometry, xmin, ymin, xmax, ymax)
        if clipped is None or clipped.is_empty:
            return clipped
        return _polygonal_only(make_valid(clipped))

    land.geometry = land.geometry.map(_clip_land_geometry)
    return land[(~land.geometry.isna()) & (~land.geometry.is_empty)].copy()


MARINE_AREA_CACHE_VERSION = "2"


def _gshhs_cache_signature(gshhg_path: Path) -> str:
    """Hash the content of the essential GSHHS shapefile components.

    Actual bytes from ``.shp``, ``.shx``, ``.dbf``, ``.prj`` and ``.cpg``
    are hashed when present, so a changed GSHHS resource invalidates the cache
    even if its filename, size or modification time happen to be unchanged.
    """

    path = Path(gshhg_path).resolve()
    allowed_suffixes = {".shp", ".shx", ".dbf", ".prj", ".cpg"}
    components = [
        item
        for item in sorted(path.parent.glob(f"{path.stem}.*"), key=lambda p: p.name.casefold())
        if item.is_file() and item.suffix.casefold() in allowed_suffixes
    ]
    if not components:
        raise FileNotFoundError(f"No GSHHS components were found for: {path}")
    digest = hashlib.sha256()
    for item in components:
        digest.update(item.name.casefold().encode("utf-8"))
        digest.update(b"\0")
        with item.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()[:20]


def _geometry_hash(geometry) -> str:
    if geometry is None or geometry.is_empty:
        return "empty"
    return hashlib.blake2b(geometry.wkb, digest_size=16).hexdigest()


def _read_marine_area_cache(cache_path: Path) -> pd.DataFrame:
    columns = [
        "grid_id",
        "geometry_hash",
        "Area_mar_gshhs_km2",
        "intersects_gshhs_land",
        "fully_covered_by_gshhs_land",
    ]
    if not cache_path.is_file():
        return pd.DataFrame(columns=columns)
    try:
        cached = pd.read_csv(cache_path, dtype={"grid_id": "string", "geometry_hash": "string"})
    except Exception:
        # A damaged cache must never prevent analysis. Ignore it and rebuild
        # values from the original spatial resources.
        return pd.DataFrame(columns=columns)
    missing = [column for column in columns if column not in cached.columns]
    if missing:
        return pd.DataFrame(columns=columns)
    cached = cached[columns].copy()
    cached["Area_mar_gshhs_km2"] = pd.to_numeric(
        cached["Area_mar_gshhs_km2"], errors="coerce"
    )
    for column in ("intersects_gshhs_land", "fully_covered_by_gshhs_land"):
        cached[column] = (
            cached[column]
            .astype("string")
            .str.strip()
            .str.casefold()
            .isin({"true", "1", "yes", "si", "sí"})
        )
    cached = cached.dropna(subset=["grid_id", "geometry_hash", "Area_mar_gshhs_km2"])
    cached = cached[cached["Area_mar_gshhs_km2"].ge(0)]
    return cached.drop_duplicates("grid_id", keep="last")


def _write_marine_area_cache(cache_path: Path, cached: pd.DataFrame) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    table = cached.copy().drop_duplicates("grid_id", keep="last").sort_values("grid_id")
    tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
    table.to_csv(tmp, index=False, encoding="utf-8")
    tmp.replace(cache_path)


def _subtract_land(
    frame: gpd.GeoDataFrame,
    land: gpd.GeoDataFrame,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
    progress_every: int = 500,
) -> tuple[list[object | None], list[bool], list[bool]]:
    total = int(len(frame))
    if land.empty:
        if progress_callback is not None and total:
            progress_callback(total, total)
        return list(frame.geometry), [False] * total, [False] * total
    spatial_index = land.sindex
    output_geometries: list[object | None] = []
    intersected_flags: list[bool] = []
    removed_flags: list[bool] = []
    for position, geometry in enumerate(frame.geometry, start=1):
        candidate_indices = list(spatial_index.query(geometry, predicate="intersects"))
        result = geometry
        intersected = bool(candidate_indices)
        if candidate_indices:
            mask = union_all(land.geometry.iloc[candidate_indices].to_numpy())
            result = make_valid(geometry.difference(mask))
        result = _polygonal_only(result)
        removed = result is None or result.is_empty
        if removed:
            output_geometries.append(None)
        else:
            output_geometries.append(result)
        intersected_flags.append(intersected)
        removed_flags.append(removed)
        if progress_callback is not None and (
            position == total or position % max(1, int(progress_every)) == 0
        ):
            progress_callback(position, total)
    return output_geometries, intersected_flags, removed_flags



def _miteco_demarcation_marine_intersection(
    frame: gpd.GeoDataFrame,
    marine_regions: gpd.GeoDataFrame | None,
) -> tuple[pd.Series, dict[object, object]]:
    """Return MITECO-demarcation marine area/geometry for coastal fallback cells.

    This fallback is only used when GSHHS returns zero marine surface while the
    official MITECO cell carries a valid positive marine-area value.  The
    demarcation intersection provides an actual marine geometry rather than
    treating the complete square as marine.
    """
    areas = pd.Series(np.nan, index=frame.index, dtype=float)
    geometries: dict[object, object] = {}
    if frame.empty or marine_regions is None or marine_regions.empty:
        return areas, geometries
    regions = marine_regions
    if regions.crs is None or frame.crs is None:
        return areas, geometries
    if regions.crs != frame.crs:
        regions = regions.to_crs(frame.crs)
    regions = regions.copy()
    regions.geometry = regions.geometry.make_valid()
    by_slug: dict[str, object] = {}
    if "Region_slug" in regions.columns:
        for slug, subset in regions.groupby("Region_slug", dropna=False):
            if pd.isna(slug) or subset.empty:
                continue
            by_slug[str(slug)] = union_all(subset.geometry.to_numpy())
    all_marine = union_all(regions.geometry.to_numpy())
    for idx, row in frame.iterrows():
        mask = by_slug.get(str(row.get("Region_slug")), all_marine)
        if mask is None or getattr(mask, "is_empty", True):
            continue
        geometry = _polygonal_only(make_valid(row.geometry.intersection(mask)))
        if geometry is None or geometry.is_empty:
            continue
        area = float(geometry.area / 1_000_000)
        if np.isfinite(area) and area > 0:
            areas.loc[idx] = area
            geometries[idx] = geometry
    return areas, geometries

def prepare_marine_grid_areas(
    grid: gpd.GeoDataFrame,
    gshhg_path: Path | None,
    *,
    cache_dir: Path | None = None,
    resolution_km: int | None = None,
    progress_callback: Callable[[str], None] | None = None,
    marine_regions: gpd.GeoDataFrame | None = None,
) -> tuple[gpd.GeoDataFrame, dict[str, object]]:
    """Calculate actual marine area, with a persistent validated cache.

    Official MITECO geometry remains unchanged for assignment. ``Area_mar_km2``
    always comes from MITECO geometry minus GSHHS land. Cached values are reused
    only when both the GSHHS signature and the exact cell-geometry fingerprint
    match the current inputs.
    """

    if gshhg_path is None:
        raise FileNotFoundError("GSHHS is required to calculate actual marine area.")
    gshhg_path = Path(gshhg_path)
    # Las mallas regionales se concatenan desde varios ficheros y pueden
    # conservar índices repetidos. El índice no forma parte de la identidad
    # analítica (esa identidad es grid_id), pero debe ser único para que las
    # asignaciones posicionales de áreas costeras no se propaguen entre filas.
    controlled = grid.copy().reset_index(drop=True)
    original_wkb = controlled.geometry.to_wkb()
    full_area = pd.to_numeric(
        controlled.get("Area_celda_km2", controlled.geometry.area / 1_000_000),
        errors="coerce",
    )
    official = pd.to_numeric(
        controlled.get("Area_mar_oficial_km2", controlled.get("Area_mar_km2")),
        errors="coerce",
    )
    maximum_area = np.maximum(full_area * 1.02, full_area + 0.01)
    valid_official = np.isfinite(official) & official.gt(0) & official.le(maximum_area)

    geometry_hashes = controlled.geometry.map(_geometry_hash).astype("string")
    gshhs_signature = _gshhs_cache_signature(gshhg_path)
    epsg = controlled.crs.to_epsg() if controlled.crs is not None else None
    crs_tag = f"epsg{epsg}" if epsg is not None else "crs_unknown"
    resolution_tag = f"{int(resolution_km)}km" if resolution_km is not None else "grid"
    cache_path = None
    cached = pd.DataFrame()
    if cache_dir is not None:
        cache_path = (
            Path(cache_dir)
            / "marine_areas"
            / f"marine_area_v{MARINE_AREA_CACHE_VERSION}_{resolution_tag}_{crs_tag}_{gshhs_signature}.csv"
        )
        cached = _read_marine_area_cache(cache_path)

    cached_lookup = {
        (str(row.grid_id), str(row.geometry_hash)): (
            float(row.Area_mar_gshhs_km2),
            bool(row.intersects_gshhs_land),
            bool(row.fully_covered_by_gshhs_land),
        )
        for row in cached.itertuples(index=False)
    }
    cached_area = []
    cached_intersects = []
    cached_removed = []
    cache_hit = []
    for grid_id, geom_hash, cell_area in zip(
        controlled["grid_id"].astype(str), geometry_hashes.astype(str), full_area
    ):
        record = cached_lookup.get((grid_id, geom_hash))
        valid_record = False
        if record is not None:
            area_value = float(record[0])
            valid_record = (
                np.isfinite(area_value)
                and area_value >= 0
                and np.isfinite(cell_area)
                and area_value <= max(float(cell_area) * 1.02, float(cell_area) + 0.01)
            )
        if valid_record:
            cached_area.append(area_value)
            cached_intersects.append(bool(record[1]))
            cached_removed.append(bool(record[2]))
            cache_hit.append(True)
        else:
            cached_area.append(np.nan)
            cached_intersects.append(False)
            cached_removed.append(False)
            cache_hit.append(False)

    hit_mask = pd.Series(cache_hit, index=controlled.index, dtype=bool)
    reused_count = int(hit_mask.sum())
    missing_count = int((~hit_mask).sum())
    if progress_callback is not None:
        if cache_path is None:
            progress_callback("Marine-area cache is disabled for this run.")
        elif reused_count == len(controlled):
            progress_callback(
                f"Valid cache: {reused_count}/{len(controlled)} cells recovered; no GSHHS recalculation is required."
            )
        elif reused_count:
            progress_callback(
                f"Partial cache: {reused_count}/{len(controlled)} cells recovered; {missing_count} will be recalculated."
            )
        else:
            progress_callback(
                f"No reusable marine areas in cache: {missing_count} cells will be calculated."
            )

    gshhs_area = pd.Series(cached_area, index=controlled.index, dtype=float)
    intersects_flags = pd.Series(cached_intersects, index=controlled.index, dtype=bool)
    removed_flags = pd.Series(cached_removed, index=controlled.index, dtype=bool)
    land_polygons_loaded = 0

    if missing_count:
        missing = controlled.loc[~hit_mask].copy()
        if progress_callback is not None:
            progress_callback("Loading GSHHS land for cells not stored in cache.")
        land = _load_gshhs_land(missing, gshhg_path)
        land_polygons_loaded = int(len(land))
        if progress_callback is not None:
            progress_callback(f"GSHHS polygons loaded: {land_polygons_loaded}.")

        def _cell_progress(done: int, total: int) -> None:
            if progress_callback is not None:
                progress_callback(f"MITECO–GSHHS clipping: {done}/{total} new cells.")

        marine_geometries, new_intersects, new_removed = _subtract_land(
            missing,
            land,
            progress_callback=_cell_progress,
            progress_every=500,
        )
        new_area = pd.Series(
            [
                float(geometry.area / 1_000_000)
                if geometry is not None and not geometry.is_empty
                else 0.0
                for geometry in marine_geometries
            ],
            index=missing.index,
            dtype=float,
        )
        gshhs_area.loc[missing.index] = new_area
        intersects_flags.loc[missing.index] = new_intersects
        removed_flags.loc[missing.index] = new_removed

        if cache_path is not None:
            current_rows = pd.DataFrame(
                {
                    "grid_id": controlled["grid_id"].astype(str).values,
                    "geometry_hash": geometry_hashes.astype(str).values,
                    "Area_mar_gshhs_km2": gshhs_area.astype(float).values,
                    "intersects_gshhs_land": intersects_flags.astype(bool).values,
                    "fully_covered_by_gshhs_land": removed_flags.astype(bool).values,
                }
            )
            combined_cache = (
                current_rows
                if cached.empty
                else pd.concat([cached, current_rows], ignore_index=True)
            )
            _write_marine_area_cache(cache_path, combined_cache)
            if progress_callback is not None:
                progress_callback(
                    f"Cache updated: {len(current_rows)} cells from this run are available for later runs."
                )

    valid_gshhs = np.isfinite(gshhs_area) & gshhs_area.gt(0)

    # Coastal fallback: a positive official MITECO marine-area flag confirms
    # eligibility, but the density denominator must come from the actual
    # fallback marine geometry (cell ∩ MITECO marine demarcation).
    fallback_candidates = (~valid_gshhs) & valid_official
    miteco_fallback_area = pd.Series(np.nan, index=controlled.index, dtype=float)
    miteco_fallback_geometries: dict[object, object] = {}
    if fallback_candidates.any() and marine_regions is not None:
        candidate_areas, candidate_geometries = _miteco_demarcation_marine_intersection(
            controlled.loc[fallback_candidates], marine_regions
        )
        miteco_fallback_area.loc[candidate_areas.index] = candidate_areas
        miteco_fallback_geometries.update(candidate_geometries)

    valid_miteco_fallback = (
        fallback_candidates
        & np.isfinite(miteco_fallback_area)
        & miteco_fallback_area.gt(0)
    )
    miteco_fallback_area = miteco_fallback_area.where(valid_miteco_fallback)

    if valid_miteco_fallback.any():
        fallback_geom_area = pd.Series(
            {
                idx: float(geometry.area / 1_000_000)
                for idx, geometry in miteco_fallback_geometries.items()
                if geometry is not None and not geometry.is_empty
            },
            dtype=float,
        ).reindex(controlled.index)
        fallback_diff = (miteco_fallback_area - fallback_geom_area).abs().where(valid_miteco_fallback)
        if fallback_diff.dropna().gt(1e-10).any():
            raise AssertionError(
                "El área marina de respaldo MITECO no coincide con la geometría marina de respaldo."
            )
        exceeds_cell = miteco_fallback_area.gt(np.maximum(full_area * 1.0000001, full_area + 1e-8))
        if exceeds_cell.fillna(False).any():
            raise AssertionError(
                "El área marina de respaldo MITECO supera la superficie geométrica de la celda."
            )

    final_area = gshhs_area.where(
        valid_gshhs, miteco_fallback_area.where(valid_miteco_fallback)
    )
    controlled["Area_mar_oficial_km2"] = official.where(valid_official)
    controlled["Area_mar_gshhs_km2"] = gshhs_area
    controlled["Area_mar_miteco_fallback_km2"] = miteco_fallback_area
    controlled["Area_celda_km2"] = full_area
    controlled["Area_mar_km2"] = final_area
    controlled["Area_mar_source"] = np.select(
        [valid_gshhs, ~valid_gshhs & valid_miteco_fallback],
        ["gshhs_clipped_geometry", "miteco_demarcation_fallback_geometry"],
        default="unavailable_no_marine_surface",
    )

    if not controlled.geometry.to_wkb().equals(original_wkb):
        raise AssertionError("Marine-surface control modified the official MITECO geometry.")
    invalid_final = ~np.isfinite(final_area) | final_area.le(0)
    comparable = valid_official & valid_gshhs
    absolute_difference = (official - gshhs_area).abs().where(comparable)
    if cache_path is None:
        cache_status = "disabled"
    elif reused_count == len(controlled):
        cache_status = "hit"
    elif reused_count:
        cache_status = "partial_hit"
    else:
        cache_status = "miss"
    return controlled, {
        "status": "passed",
        "method": "gshhs_clipped_geometry_with_miteco_demarcation_fallback",
        "density_denominator": "marine_geometry_km2_gshhs_primary_miteco_fallback",
        "official_geometry_retained_for_assignment": True,
        "marine_flag_filter_applied": False,
        "gshhs_required": True,
        "gshhs_signature": gshhs_signature,
        "gshhs_land_polygons_loaded": int(land_polygons_loaded),
        "cells_total": int(len(controlled)),
        "cells_intersecting_gshhs_land": int(intersects_flags.sum()),
        "cells_fully_covered_by_gshhs_land": int(removed_flags.sum()),
        "cells_with_valid_official_area": int(valid_official.sum()),
        "cells_using_gshhs_marine_area": int(valid_gshhs.sum()),
        "cells_using_miteco_demarcation_fallback": int(valid_miteco_fallback.sum()),
        "cells_without_positive_marine_area": int(invalid_final.sum()),
        "cells_with_official_gshhs_comparison": int(comparable.sum()),
        "max_abs_official_vs_gshhs_km2": (
            float(absolute_difference.max()) if comparable.any() else None
        ),
        "marine_area_cache_version": MARINE_AREA_CACHE_VERSION,
        "marine_area_cache_status": cache_status,
        "marine_area_cache_cells_reused": reused_count,
        "marine_area_cache_cells_computed": missing_count,
        "marine_area_cache_file": str(cache_path) if cache_path is not None else None,
        "area_source_counts": {
            str(key): int(value)
            for key, value in controlled["Area_mar_source"].value_counts(dropna=False).items()
        },
    }

def clip_occupied_cells_with_land(
    occupied: gpd.GeoDataFrame,
    gshhg_path: Path | None,
    enabled: bool = True,
    marine_regions: gpd.GeoDataFrame | None = None,
) -> tuple[gpd.GeoDataFrame, dict[str, object]]:
    if not enabled:
        raise ValueError(
            "GSHHS clipping cannot be disabled in a complete cartographic run."
        )
    land = _load_gshhs_land(occupied, gshhg_path)
    if land.empty:
        return occupied.copy(), {
            "land_polygons_loaded": 0,
            "cells_clipped": 0,
            "cells_removed": 0,
            "status": "loaded_empty_bbox",
            "method": "GSHHS_difference_marine_geometry",
        }
    output_geometries, intersected_flags, removed_flags = _subtract_land(occupied, land)
    fallback_mask = occupied.get("Area_mar_source", pd.Series("", index=occupied.index)).astype("string").eq(
        "miteco_demarcation_fallback_geometry"
    )
    fallback_count = 0
    if fallback_mask.any() and marine_regions is not None:
        _, fallback_geometries = _miteco_demarcation_marine_intersection(
            occupied.loc[fallback_mask], marine_regions
        )
        position_by_index = {idx: pos for pos, idx in enumerate(occupied.index)}
        for idx, geometry in fallback_geometries.items():
            output_geometries[position_by_index[idx]] = geometry
            fallback_count += 1
    clipped_count = int(sum(intersected_flags))
    removed_count = int(sum(removed_flags))
    visual = occupied.copy()
    visual.geometry = output_geometries
    visual = visual[(~visual.geometry.isna()) & (~visual.geometry.is_empty)].copy()
    return visual, {
        "land_polygons_loaded": int(len(land)),
        "cells_clipped": int(clipped_count),
        "cells_removed": int(removed_count),
        "cells_using_miteco_demarcation_fallback_geometry": int(fallback_count),
        "status": "loaded",
        "method": "GSHHS_difference_with_MITECO_demarcation_fallback",
    }
