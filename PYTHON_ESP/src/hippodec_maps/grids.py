"""Preparación, descubrimiento y lectura de las mallas marinas MITECO."""

from __future__ import annotations

import json
import logging
import time
import re
import shutil
import stat
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from shapely import box, union_all

from .config import REGIONS, ascii_slug, normalize_region


LOGGER = logging.getLogger("hippodec_maps")


GRID_EXTENSIONS = {".shp", ".shx", ".dbf", ".prj", ".cpg", ".sbn", ".sbx", ".qpj"}
GSHHG_EXTENSIONS = {".shp", ".shx", ".dbf", ".prj", ".cpg", ".sbn", ".sbx", ".qpj"}


def prepare_grid_root(source: Path, cache_dir: Path) -> Path:
    if source.is_dir():
        return source
    if source.suffix.lower() != ".zip":
        raise ValueError(f"El origen de la malla no es ni una carpeta ni un archivo ZIP: {source}")
    signature = {
        "zip_size": source.stat().st_size,
        "zip_mtime_ns": source.stat().st_mtime_ns,
    }
    destination = (
        cache_dir
        / f"Mallas_marinas_MITECO_{signature['zip_size']}_{signature['zip_mtime_ns']}"
    )
    marker = destination / "extraction_info.json"
    if marker.exists():
        try:
            if json.loads(marker.read_text(encoding="utf-8")) == signature:
                return destination
        except (OSError, json.JSONDecodeError):
            pass

    destination.mkdir(parents=True, exist_ok=True)
    with ZipFile(source) as archive:
        infos = archive.infolist()
        total_size = sum(item.file_size for item in infos)
        if total_size > 5_000_000_000:
            raise ValueError(
                "El ZIP de la malla supera el límite de seguridad de 5 GB una vez descomprimido."
            )
        seen_names: set[str] = set()
        for item in infos:
            posix = PurePosixPath(item.filename)
            mode = (item.external_attr >> 16) & 0xFFFF
            if posix.is_absolute() or ".." in posix.parts or stat.S_ISLNK(mode):
                raise ValueError(f"Entrada no segura dentro del archivo ZIP: {item.filename}")
            normalized_name = item.filename.casefold()
            if normalized_name in seen_names:
                raise ValueError(f"Entrada duplicada dentro del archivo ZIP: {item.filename}")
            seen_names.add(normalized_name)
            if (
                item.file_size > 0
                and item.compress_size > 0
                and item.file_size / item.compress_size > 1000
            ):
                raise ValueError(
                    f"Proporción de compresión sospechosa dentro del archivo ZIP: {item.filename}"
                )
            if (
                item.is_dir()
                or Path(item.filename).suffix.lower() not in GRID_EXTENSIONS
            ):
                continue
            parts = list(posix.parts)
            if parts and parts[0].casefold() == "mallas_marinas_miteco":
                parts = parts[1:]
            if not parts:
                continue
            output = destination.joinpath(*parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as src, output.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    marker.write_text(json.dumps(signature, indent=2), encoding="utf-8")
    return destination


def prepare_gshhg_root(source: Path | None, cache_dir: Path) -> Path | None:
    """Devuelve un shapefile GSHHS legible y extrae de forma segura un ZIP suministrado."""

    if source is None:
        return None
    if source.is_dir():
        matches = sorted(source.rglob("GSHHS_h_L1.shp"))
        return matches[0] if matches else None
    if source.suffix.lower() != ".zip":
        return source
    signature = {"zip_size": source.stat().st_size, "zip_mtime_ns": source.stat().st_mtime_ns}
    destination = cache_dir / f"GSHHS_{signature['zip_size']}_{signature['zip_mtime_ns']}"
    marker = destination / "extraction_info.json"
    shapefile = destination / "GSHHS_h_L1.shp"
    if marker.exists() and shapefile.exists():
        try:
            if json.loads(marker.read_text(encoding="utf-8")) == signature:
                return shapefile
        except (OSError, json.JSONDecodeError):
            pass
    destination.mkdir(parents=True, exist_ok=True)
    with ZipFile(source) as archive:
        selected = []
        seen_names: set[str] = set()
        for item in archive.infolist():
            posix = PurePosixPath(item.filename)
            mode = (item.external_attr >> 16) & 0xFFFF
            if posix.is_absolute() or ".." in posix.parts or stat.S_ISLNK(mode):
                raise ValueError(f"Entrada no segura dentro del ZIP GSHHS: {item.filename}")
            normalized = item.filename.casefold()
            if normalized in seen_names:
                raise ValueError(f"Entrada duplicada dentro del ZIP GSHHS: {item.filename}")
            seen_names.add(normalized)
            if item.is_dir() or Path(item.filename).suffix.lower() not in GSHHG_EXTENSIONS:
                continue
            if Path(item.filename).name.casefold().startswith("gshhs_h_l1."):
                selected.append(item)
        required = {Path(item.filename).suffix.lower() for item in selected}
        if not {".shp", ".shx", ".dbf", ".prj"}.issubset(required):
            raise FileNotFoundError("El ZIP GSHHS no contiene el shapefile GSHHS_h_L1 completo.")
        for item in selected:
            output = destination / Path(item.filename).name
            with archive.open(item) as src, output.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    marker.write_text(json.dumps(signature, indent=2), encoding="utf-8")
    return shapefile


def _grid_resolution(path: Path) -> int | None:
    text = ascii_slug(path)
    match = re.search(r"malla(1|5|10)x\1(?:km)?", text.replace("_", ""))
    if match:
        return int(match.group(1))
    compact = str(path).lower().replace("_", "")
    for value in (1, 5, 10):
        if f"malla{value}x{value}" in compact or f"{value}x{value}km" in compact:
            return value
    return None


def region_from_grid_path(path: Path) -> str:
    text = ascii_slug(path)
    if "penbal" in text:
        return "levantina"
    return normalize_region(text)


def discover_grid_files(
    root: Path, resolution_km: int, selected_region: str
) -> list[Path]:
    files = [
        path
        for path in root.rglob("*.shp")
        if _grid_resolution(path) == resolution_km
        and "demarcaciones_marinas_20220909" not in ascii_slug(path)
    ]
    if not files:
        raise FileNotFoundError(
            f"No se encontraron mallas de {resolution_km} km en {root}"
        )
    has_penbal = any("penbal" in ascii_slug(path) for path in files)
    has_specific = any(
        any(
            token in ascii_slug(path)
            for token in ("noratlant", "sudatlant", "estrecho", "alboran", "levantino")
        )
        for path in files
    )
    if has_penbal and has_specific:
        files = [path for path in files if "penbal" not in ascii_slug(path)]
    if selected_region != "all":
        files = [
            path for path in files if region_from_grid_path(path) == selected_region
        ]
    if not files:
        raise FileNotFoundError(
            f"No se encontró ninguna malla de {resolution_km} km para la región {selected_region}."
        )
    return sorted(files, key=lambda p: str(p).casefold())


def _column_case_insensitive(
    columns: list[str], candidates: tuple[str, ...]
) -> str | None:
    lookup = {str(column).lower(): str(column) for column in columns}
    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]
    return None


def _bbox_for_points(
    points_3035: gpd.GeoDataFrame,
    source_crs: object,
    region_slug: str,
    buffer_m: float,
) -> tuple[float, float, float, float] | None:
    values = points_3035["Region_slug"].astype("string").str.strip().str.casefold()
    missing = (
        points_3035["Region_slug"].isna()
        | values.isin({"", "nan", "none", "no data", "sin datos", "sin_datos", "no region"})
    )
    # Un punto sin intersección directa con una demarcación puede indicar aun
    # así qué archivo de malla regional debe leerse. Se incluye en la extensión
    # de cada candidato; la intersección con la malla oficial resuelve después
    # la región final.
    subset = points_3035[values.eq(region_slug.casefold()) | missing]
    if subset.empty:
        return None
    local = subset.to_crs(source_crs)
    minx, miny, maxx, maxy = local.total_bounds
    return (minx - buffer_m, miny - buffer_m, maxx + buffer_m, maxy + buffer_m)




def _tiled_bboxes_for_points(
    points_3035: gpd.GeoDataFrame,
    source_crs: object,
    region_slug: str,
    buffer_m: float,
    source_bounds: tuple[float, float, float, float] | list[float] | np.ndarray,
    tile_size_m: float = 50_000.0,
) -> list[tuple[float, float, float, float]]:
    """Build compact read windows around observations for very fine grids.

    A single bounding box spanning distant observations can read many unused
    MITECO cells at any resolution, especially at 1 km. The tiled windows keep
    every cell that can participate in point assignment while avoiding those
    unnecessary intermediate geometries. The same lossless strategy is used
    at 1, 5 and 10 km.
    """

    values = points_3035["Region_slug"].astype("string").str.strip().str.casefold()
    missing = (
        points_3035["Region_slug"].isna()
        | values.isin({"", "nan", "none", "no data", "sin datos", "sin_datos", "no region"})
    )
    subset = points_3035[values.eq(region_slug.casefold()) | missing]
    if subset.empty:
        return []

    local = subset.to_crs(source_crs).copy()
    minx, miny, maxx, maxy = [float(value) for value in source_bounds]
    x = local.geometry.x
    y = local.geometry.y
    # Unresolved-region points are considered only for grid files whose real
    # spatial extent they can reach. This prevents the same mainland/Canary
    # observation from expanding every regional read window.
    local = local.loc[
        x.between(minx - buffer_m, maxx + buffer_m)
        & y.between(miny - buffer_m, maxy + buffer_m)
    ].copy()
    if local.empty:
        return []

    tile_size_m = max(float(tile_size_m), float(buffer_m) * 4.0)
    local["_tile_x"] = np.floor(local.geometry.x / tile_size_m).astype("int64")
    local["_tile_y"] = np.floor(local.geometry.y / tile_size_m).astype("int64")

    windows: list[tuple[float, float, float, float]] = []
    for _, group in local.groupby(["_tile_x", "_tile_y"], sort=False):
        gx0, gy0, gx1, gy1 = group.total_bounds
        bbox = (
            max(minx, float(gx0) - buffer_m),
            max(miny, float(gy0) - buffer_m),
            min(maxx, float(gx1) + buffer_m),
            min(maxy, float(gy1) + buffer_m),
        )
        if bbox[0] <= bbox[2] and bbox[1] <= bbox[3]:
            windows.append(bbox)
    return windows


def _read_grid_near_points(
    path: Path,
    info: dict[str, object],
    points_3035: gpd.GeoDataFrame,
    region_slug: str,
    resolution_km: int,
    bbox_buffer_factor: float,
) -> tuple[gpd.GeoDataFrame | None, list[tuple[float, float, float, float]], str]:
    """Read only the portion of a grid that can be used by this run."""

    buffer_m = resolution_km * 1000 * bbox_buffer_factor
    source_bounds = info.get("total_bounds")
    if source_bounds is None:
        bbox = _bbox_for_points(points_3035, info["crs"], region_slug, buffer_m)
        if bbox is None:
            return None, [], "single_bbox_fallback"
        layer = gpd.read_file(path, bbox=bbox, engine="pyogrio")
        return layer, [bbox], "single_bbox_fallback"

    # Use the same compact local-window strategy at 1, 5 and 10 km.  The
    # margin is still resolution_km * bbox_buffer_factor, so every cell that
    # can participate in direct or nearest assignment is retained.  Only
    # unused cells lying between distant observation clusters are avoided.
    windows = _tiled_bboxes_for_points(
        points_3035,
        info["crs"],
        region_slug,
        buffer_m,
        source_bounds,
    )
    strategy = f"tiled_bbox_{resolution_km}km"
    if not windows:
        return None, [], strategy

    # A single spatial mask avoids reopening/scanning the same source for
    # every observation window. The mask is the exact union of the original
    # rectangles, with no simplification or change to their buffer.
    # Without GEOS, GDAL may apply envelope-only filtering; preserve the
    # original reads in that case, and for degenerate edge rectangles.
    use_union = (
        getattr(pyogrio, "__gdal_geos_version__", None) is not None
        and all(x0 < x1 and y0 < y1 for x0, y0, x1, y1 in windows)
    )
    if use_union:
        LOGGER.info('  Malla %dkm: %s; %d ventanas en una sola lectura.', resolution_km, path.name, len(windows))
        mask = union_all([box(*bounds) for bounds in windows])
        layer = gpd.read_file(path, mask=mask, engine="pyogrio", fid_as_index=True)
        strategy = f"union_windows_{resolution_km}km"
        if layer.empty:
            return None, windows, strategy
    else:
        LOGGER.info('  Malla %dkm: %s; lectura por ventanas compatible (%d).', resolution_km, path.name, len(windows))
        chunks: list[gpd.GeoDataFrame] = []
        for bbox in windows:
            chunk = gpd.read_file(path, bbox=bbox, engine="pyogrio", fid_as_index=True)
            if not chunk.empty:
                chunks.append(chunk)
        if not chunks:
            return None, windows, strategy
        layer = gpd.GeoDataFrame(pd.concat(chunks, axis=0), geometry="geometry", crs=chunks[0].crs)

    # Stable source FID order preserves deterministic boundary-cell ties.
    layer = layer.loc[~layer.index.duplicated(keep="first")].sort_index()
    layer = layer.reset_index(drop=True)
    return layer, windows, strategy


def load_grids(
    grid_root: Path,
    resolution_km: int,
    selected_region: str,
    points_3035: gpd.GeoDataFrame,
    target_crs: int = 3035,
    bbox_buffer_factor: float = 1.25,
) -> tuple[gpd.GeoDataFrame, list[dict[str, object]]]:
    files = discover_grid_files(grid_root, resolution_km, selected_region)
    frames: list[gpd.GeoDataFrame] = []
    inventory: list[dict[str, object]] = []
    order_start = 0
    for path in files:
        file_started = time.perf_counter()
        LOGGER.info('  Abriendo malla %dkm: %s', resolution_km, path.name)
        region_slug = region_from_grid_path(path)
        info = pyogrio.read_info(path)
        if not info.get("crs"):
            raise ValueError(f"La malla no tiene un CRS definido: {path}")
        layer, read_windows, read_strategy = _read_grid_near_points(
            path,
            info,
            points_3035,
            region_slug,
            resolution_km,
            bbox_buffer_factor,
        )
        LOGGER.info('  Lectura %dkm: %d celdas en %.2f s.', resolution_km, 0 if layer is None else len(layer), time.perf_counter() - file_started)
        if layer is None:
            inventory.append(
                {
                    "file": str(path),
                    "region": region_slug,
                    "rows_loaded": 0,
                    "skipped_no_points": len(read_windows) == 0,
                    "read_strategy": read_strategy,
                    "bbox_filter_count": len(read_windows),
                }
            )
            continue
        if layer.empty:
            inventory.append(
                {
                    "file": str(path),
                    "region": region_slug,
                    "rows_loaded": 0,
                    "skipped_no_points": False,
                    "read_strategy": read_strategy,
                    "bbox_filter_count": len(read_windows),
                }
            )
            continue
        if layer.crs is None:
            raise ValueError(f"La malla no tiene un CRS definido: {path}")

        columns = [str(column) for column in layer.columns]

        # Algunos archivos oficiales MITECO contienen celdas costeras completas
        # con una marca MARINO. No se descartan aquí las filas MARINO=0: una
        # observación marina válida puede caer en una celda costera mixta cuya
        # marca no sea exclusivamente marina. Las filas terrestres vacías no
        # entran en las métricas ocupadas, pero conservarlas evita perder
        # observaciones válidas.
        marine_col = _column_case_insensitive(
            columns, ("MARINO", "marine", "is_marine", "marino_flag")
        )
        marine_rows_before = int(len(layer))
        marine_filter_applied = False
        marine_rows_removed = 0
        if marine_col is not None:
            marine_value = layer[marine_col]
            if pd.api.types.is_bool_dtype(marine_value):
                marine_flag = marine_value.fillna(False)
            else:
                marine_flag = (
                    marine_value.astype("string")
                    .str.strip()
                    .str.casefold()
                    .isin({"1", "true", "t", "yes", "y", "si", "sí", "marino", "marine"})
                )
            layer["official_marine_flag"] = marine_flag.astype(bool).values
        else:
            # Older and clipped MITECO products have no flag. Their supplied
            # las filas siguen disponibles para asignar puntos, como en la
            # versión española anterior.
            layer["official_marine_flag"] = True

        columns = [str(column) for column in layer.columns]
        code_candidates = {
            1: (
                "grid_id",
                "id",
                "cell_id",
                "id_celda",
                "codigo",
                "cod",
                "COD1X1",
                "UTMCODE1X1",
            ),
            5: ("grid_id", "id", "cell_id", "id_celda", "codigo", "cod", "COD5X5"),
            10: (
                "grid_id",
                "id",
                "cell_id",
                "id_celda",
                "codigo",
                "cod",
                "CUADRICULA",
                "COD_INB",
            ),
        }[resolution_km]
        code_col = _column_case_insensitive(columns, code_candidates)
        if code_col is None:
            codes = pd.Series(
                [f"fila_{idx + 1}" for idx in range(len(layer))], index=layer.index
            )
        else:
            codes = layer[code_col].astype("string").str.strip()
            fallback = pd.Series(
                [f"fila_{idx + 1}" for idx in range(len(layer))],
                index=layer.index,
                dtype="string",
            )
            codes = codes.mask(codes.isna() | codes.eq(""), fallback)

        # Los campos de superficie MITECO se conservan únicamente para auditoría.
        # El denominador se recalcula siempre como celda menos tierra GSHHS.
        area_col = _column_case_insensitive(
            columns,
            (
                "area_mar_km2",
                "marine_area_km2",
                "superficie_marina_km2",
                "area_km2",
                "area_mar",
                "superficie_marina",
            ),
        )
        ignored_generic_area_col = _column_case_insensitive(
            columns, ("superficie", "area")
        )
        if area_col is not None:
            area = pd.to_numeric(
                layer[area_col].astype("string").str.replace(",", ".", regex=False),
                errors="coerce",
            )
        else:
            area = pd.Series(np.nan, index=layer.index, dtype=float)

        layer = layer.to_crs(target_crs)
        layer.geometry = layer.geometry.make_valid()
        geometric_area = layer.geometry.area / 1_000_000
        # Los nombres sin sufijo de unidad se mantienen como identificadores internos estables.
        # productos MITECO antiguos. Se infiere m2 únicamente cuando su escala
        # respecto al área geométrica demuestra esa unidad de forma inequívoca.
        area_unit = "km2"
        if area_col is not None and area_col.casefold() in {
            "area_mar",
            "superficie_marina",
        }:
            positive = area[np.isfinite(area) & area.gt(0)]
            comparable = geometric_area.loc[positive.index]
            ratios = positive / comparable.where(comparable.gt(0))
            median_ratio = float(ratios.replace([np.inf, -np.inf], np.nan).median())
            if np.isfinite(median_ratio) and median_ratio > 10_000:
                area = area / 1_000_000
                area_unit = "m2_converted_to_km2"

        valid_official_area = (
            np.isfinite(area)
            & area.gt(0)
            & area.le(np.maximum(geometric_area * 1.02, geometric_area + 0.01))
        )
        official_area = area.where(valid_official_area, np.nan)

        source_tag = ascii_slug(path.stem)
        layer["official_cell_code"] = codes.astype(str).values
        layer["grid_id"] = [
            f"{region_slug}:{resolution_km}km:{source_tag}:{code}"
            for code in layer["official_cell_code"]
        ]
        if layer["grid_id"].duplicated().any():
            occurrence = layer.groupby("grid_id").cumcount()
            layer["grid_id"] = layer["grid_id"] + occurrence.map(
                lambda value: f":{value}" if value else ""
            )
        layer["Area_mar_km2"] = official_area.astype(float).values
        layer["Area_mar_oficial_km2"] = official_area.astype(float).values
        layer["Area_celda_km2"] = geometric_area.astype(float).values
        layer["Area_mar_source"] = np.where(
            valid_official_area,
            f"official:{area_col}" if area_col else "official:missing",
            "pending_gshhs_clipping",
        )
        layer["Region_slug"] = region_slug
        layer["Region_MITECO"] = REGIONS[region_slug]["label"]
        layer["resolution_km"] = int(resolution_km)
        layer["source_file"] = path.name
        layer["grid_order"] = np.arange(
            order_start, order_start + len(layer), dtype=int
        )
        order_start += len(layer)
        keep = [
            "grid_id",
            "official_cell_code",
            "Area_mar_km2",
            "Area_mar_oficial_km2",
            "Area_celda_km2",
            "Area_mar_source",
            "official_marine_flag",
            "Region_slug",
            "Region_MITECO",
            "resolution_km",
            "source_file",
            "grid_order",
            "geometry",
        ]
        frames.append(layer[keep])
        LOGGER.info('  Malla %dkm preparada: %d celdas; total por archivo %.2f s.', resolution_km, len(layer), time.perf_counter() - file_started)
        inventory.append(
            {
                "file": str(path),
                "region": region_slug,
                "source_crs": str(info["crs"]),
                "rows_loaded": int(len(layer)),
                "rows_source": marine_rows_before,
                "rows_removed_non_marine": marine_rows_removed,
                "marine_flag_column": marine_col,
                "marine_filter_applied": marine_filter_applied,
                "bbox_filter": (
                    [float(value) for value in read_windows[0]]
                    if len(read_windows) == 1
                    else None
                ),
                "bbox_filter_count": len(read_windows),
                "read_strategy": read_strategy,
                "id_column": code_col,
                "area_column": area_col,
                "area_unit": area_unit if area_col else None,
                "official_area_valid_rows": int(valid_official_area.sum()),
                "official_area_invalid_or_missing_rows": int(
                    (~valid_official_area).sum()
                ),
                "ignored_generic_area_column": (
                    ignored_generic_area_col if area_col is None else None
                ),
            }
        )
    if not frames:
        raise ValueError(
            "La carga de las mallas no produjo celdas alrededor de las observaciones."
        )
    combined = gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True), crs=f"EPSG:{target_crs}"
    )
    if combined["grid_id"].duplicated().any():
        raise ValueError(
            "Se generaron valores de grid_id duplicados al combinar las mallas."
        )
    # El recorte final de todas las celdas contra GSHHS se realiza en
    # ``prepare_marine_grid_areas`` antes de asignar observaciones. Hasta ese
    # momento los NaN son deliberados y nunca se usan para calcular densidad.
    return combined, inventory
