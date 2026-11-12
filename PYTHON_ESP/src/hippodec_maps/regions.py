"""Carga de demarcaciones MITECO y asignación de regiones."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

from .config import REGIONS, normalize_region
from .sampling import add_sampling_event_ids


def load_demarcations(path: Path, target_crs: int = 3035) -> gpd.GeoDataFrame:
    regions = gpd.read_file(path, engine="pyogrio")
    if regions.empty:
        raise ValueError(f"La capa de demarcaciones marinas está vacía: {path}")
    if regions.crs is None:
        raise ValueError(f"La capa de demarcaciones marinas no tiene CRS: {path}")
    name_column = "text" if "text" in regions.columns else None
    if name_column is None:
        for candidate in ("nombre", "name", "demarcacion", "subregion"):
            if candidate in regions.columns:
                name_column = candidate
                break
    if name_column is None:
        raise ValueError(
            "La capa de demarcaciones marinas no tiene un campo de nombre reconocible."
        )
    regions = regions[[name_column, "geometry"]].rename(
        columns={name_column: "region_source"}
    )
    regions["Region_slug"] = regions["region_source"].map(normalize_region)
    regions["Region_MITECO"] = regions["Region_slug"].map(lambda x: REGIONS[x]["label"])
    regions = regions.to_crs(target_crs)
    regions.geometry = regions.geometry.make_valid()
    return regions


def observations_to_points(
    data: pd.DataFrame, target_crs: int = 3035
) -> gpd.GeoDataFrame:
    frames: list[gpd.GeoDataFrame] = []
    for epsg in data["EPSG"].dropna().astype(int).drop_duplicates().tolist():
        subset = data[data["EPSG"].astype(int).eq(epsg)].copy()
        points = gpd.GeoDataFrame(
            subset,
            geometry=gpd.points_from_xy(subset["X"], subset["Y"]),
            crs=f"EPSG:{epsg}",
        ).to_crs(target_crs)
        frames.append(points)
    if not frames:
        raise ValueError("No hay valores EPSG válidos con los que construir los puntos.")
    result = gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True), crs=f"EPSG:{target_crs}"
    )
    result["obs_id"] = range(1, len(result) + 1)
    result = add_sampling_event_ids(result)
    return result


def assign_observation_regions(
    points: gpd.GeoDataFrame, regions: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    region_cols = regions[["Region_slug", "Region_MITECO", "geometry"]]
    joined = gpd.sjoin(points, region_cols, how="left", predicate="intersects")
    joined = joined.sort_values(["obs_id", "index_right"], na_position="last")
    joined = joined.drop_duplicates("obs_id", keep="first").drop(
        columns=["index_right"]
    )
    joined["Region_slug"] = joined["Region_slug"].fillna("sin_datos")
    joined["Region_MITECO"] = joined["Region_MITECO"].fillna("No data")
    return gpd.GeoDataFrame(joined, geometry="geometry", crs=points.crs)


def filter_region(points: gpd.GeoDataFrame, selected_region: str) -> gpd.GeoDataFrame:
    if selected_region == "all":
        return points.copy()
    filtered = points[points["Region_slug"].eq(selected_region)].copy()
    if filtered.empty:
        raise ValueError(
            f"No quedan observaciones dentro de {REGIONS[selected_region]['label']}."
        )
    return filtered


def boundaries_for_map(
    regions: gpd.GeoDataFrame, selected_region: str, simplify_m: float = 100
) -> dict:
    subset = (
        regions
        if selected_region == "all"
        else regions[regions["Region_slug"].eq(selected_region)]
    )
    subset = subset.copy()
    if simplify_m > 0:
        subset.geometry = subset.geometry.simplify(simplify_m, preserve_topology=True)
    return subset.to_crs(4326).__geo_interface__
