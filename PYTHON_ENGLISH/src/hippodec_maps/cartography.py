"""Common cartographic context, with optional external coastline support."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from shapely import make_valid
from shapely.geometry import box, mapping

from .source_notices import add_cartographic_notice


@dataclass(frozen=True)
class MapContext:
    """Land, coastline, and extent shared by all maps."""

    land: gpd.GeoDataFrame
    coastline: gpd.GeoDataFrame
    bounds: tuple[float, float, float, float]
    qa: dict[str, Any]


def _safe_property(value: Any) -> Any:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if np.isfinite(number) else None
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    return str(value)


def feature_collection(
    frame: gpd.GeoDataFrame,
    fields: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Convert a layer to GeoJSON without NaN or NumPy-specific types."""

    if frame.empty:
        return {"type": "FeatureCollection", "features": []}
    source = frame.to_crs(4326) if frame.crs != "EPSG:4326" else frame.copy()
    chosen = [field for field in (fields or []) if field in source.columns]
    features: list[dict[str, Any]] = []
    for _, row in source.iterrows():
        geometry = row.geometry
        if geometry is None or geometry.is_empty:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(geometry),
                "properties": {
                    field: _safe_property(row[field]) for field in chosen
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _padded_bounds(reference: gpd.GeoDataFrame) -> tuple[float, float, float, float]:
    if reference.empty or reference.crs is None:
        raise ValueError("The cartographic context cannot be calculated without geometries and a CRS.")
    minimum_x, minimum_y, maximum_x, maximum_y = reference.to_crs(4326).total_bounds
    span_x = max(float(maximum_x - minimum_x), 0.01)
    span_y = max(float(maximum_y - minimum_y), 0.01)
    pad_x = max(0.25, 0.06 * span_x)
    pad_y = max(0.25, 0.06 * span_y)
    return (
        max(-180.0, float(minimum_x) - pad_x),
        max(-85.0, float(minimum_y) - pad_y),
        min(180.0, float(maximum_x) + pad_x),
        min(85.0, float(maximum_y) + pad_y),
    )


def load_map_context(
    gshhg_path: Path | None,
    reference: gpd.GeoDataFrame,
    simplify_m: float = 200.0,
) -> MapContext:
    """Load and clip GSHHG when available.

    The official MITECO marine grid remains sufficient for analysis and map
    extents.  When GSHHG is absent, no substitute land/coastline geometry is
    invented or embedded in HTML outputs; the basemap supplies the visual
    context instead.
    """

    bounds = _padded_bounds(reference)
    if gshhg_path is None:
        empty = gpd.GeoDataFrame(geometry=[], crs=4326)
        return MapContext(
            land=empty,
            coastline=empty.copy(),
            bounds=bounds,
            qa={
                "source": None,
                "status": "not_available_optional",
                "land_features": 0,
                "coastline_features": 0,
                "simplify_m": float(simplify_m),
                "bounds_wgs84": [float(value) for value in bounds],
                "html_custom_land_coast_published": False,
            },
        )
    information = pyogrio.read_info(gshhg_path)
    source_crs = information.get("crs")
    if not source_crs:
        raise ValueError(f"GSHHG has no defined CRS: {gshhg_path}")
    clip_wgs84 = gpd.GeoSeries([box(*bounds)], crs=4326)
    clip_source = clip_wgs84.to_crs(source_crs).iloc[0]
    land_source = gpd.read_file(
        gshhg_path, bbox=clip_source.bounds, engine="pyogrio"
    )[["geometry"]]
    if land_source.empty:
        empty = gpd.GeoDataFrame(geometry=[], crs=4326)
        return MapContext(
            land=empty,
            coastline=empty.copy(),
            bounds=bounds,
            qa={
                "source": str(gshhg_path),
                "status": "loaded_empty_bbox",
                "land_features": 0,
                "coastline_features": 0,
                "simplify_m": float(simplify_m),
                "html_custom_land_coast_published": False,
            },
        )

    land_source.geometry = land_source.geometry.map(make_valid)
    # La costa se obtiene antes del recorte para no dibujar como litoral el borde
    # rectangular de la extensión del mapa.
    coast_source = gpd.GeoDataFrame(
        geometry=land_source.geometry.boundary, crs=land_source.crs
    )
    land_source.geometry = land_source.geometry.intersection(clip_source)
    coast_source.geometry = coast_source.geometry.intersection(clip_source)
    land_source = land_source[~land_source.geometry.is_empty].copy()
    coast_source = coast_source[~coast_source.geometry.is_empty].copy()

    projected_crs = reference.crs if not reference.crs.is_geographic else "EPSG:3035"
    land = land_source.to_crs(projected_crs)
    coastline = coast_source.to_crs(projected_crs)
    if simplify_m > 0:
        land.geometry = land.geometry.simplify(simplify_m, preserve_topology=True)
        coastline.geometry = coastline.geometry.simplify(
            simplify_m, preserve_topology=True
        )
    land = land.to_crs(4326)
    coastline = coastline.to_crs(4326)
    land = land[(~land.geometry.isna()) & (~land.geometry.is_empty)].copy()
    coastline = coastline[
        (~coastline.geometry.isna()) & (~coastline.geometry.is_empty)
    ].copy()
    return MapContext(
        land=land,
        coastline=coastline,
        bounds=bounds,
        qa={
            "source": str(gshhg_path),
            "status": "loaded",
            "land_features": int(len(land)),
            "coastline_features": int(len(coastline)),
            "simplify_m": float(simplify_m),
            "bounds_wgs84": [float(value) for value in bounds],
            "html_custom_land_coast_published": False,
        },
    )


def add_map_context(ax, context: MapContext) -> None:
    """Draw sea, land, and coastline in a stable order on a Matplotlib axis."""

    ax.set_facecolor("#dceff5")
    if not context.land.empty:
        context.land.plot(
            ax=ax,
            color="#efeee9",
            edgecolor="none",
            linewidth=0,
            zorder=0,
        )
    if not context.coastline.empty:
        context.coastline.plot(
            ax=ax,
            color="#303030",
            linewidth=0.55,
            zorder=6,
        )
    minimum_x, minimum_y, maximum_x, maximum_y = context.bounds
    ax.set_xlim(minimum_x, maximum_x)
    ax.set_ylim(minimum_y, maximum_y)
    ax.set_aspect("equal", adjustable="box")
    add_cartographic_notice(ax.figure)
