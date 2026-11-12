"""Reproducible observation-event proxy.

This module defines event identity only. It provides the canonical event identifier used throughout the analytical workflow.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

import geopandas as gpd
import numpy as np
import pandas as pd


DEFAULT_EVENT_PRECISION_M = 1.0


def _normalize_observer(value: object) -> str | None:
    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = unicodedata.normalize("NFKC", str(value))
    text = re.sub(r"\s+", " ", text).strip().casefold()
    return text or None


def _metric_crs_uses_metres(frame: gpd.GeoDataFrame) -> bool:
    if frame.crs is None or not frame.crs.is_projected:
        return False
    axes = getattr(frame.crs, "axis_info", None) or []
    if not axes:
        return True
    units = {str(getattr(axis, "unit_name", "")).casefold() for axis in axes}
    return all(unit in {"metre", "meter", "metres", "meters"} for unit in units if unit)


def add_sampling_event_ids(
    points: gpd.GeoDataFrame,
    *,
    coordinate_precision_m: float = DEFAULT_EVENT_PRECISION_M,
    date_column: str = "Fecha_aux",
    observer_column: str = "Observer",
    source_row_column: str = "source_row",
) -> gpd.GeoDataFrame:
    """Add a stable event identifier without changing row order.

    The canonical key is date + normalized observer + metric position quantized
    to ``coordinate_precision_m``. Species, abundance, ``Id`` and grid
    resolution do not participate in event identity.

    If observer is missing, ``source_row`` is used as a conservative fallback
    so records that may belong to different observers/events are not merged.
    This can under-group those cases, but avoids inventing an unsupported
    equivalence.
    """

    if coordinate_precision_m <= 0 or not np.isfinite(coordinate_precision_m):
        raise ValueError("coordinate_precision_m must be a positive finite number.")
    if date_column not in points.columns:
        raise ValueError(f"Required date column is missing: {date_column}")
    if points.geometry.name not in points.columns:
        raise ValueError("No active geometry column was found.")
    if not _metric_crs_uses_metres(points):
        raise ValueError(
            "Observation events must be built in a projected CRS with metre units."
        )

    out = points.copy()
    dates = pd.to_datetime(out[date_column], errors="coerce")
    invalid_date = dates.isna()
    invalid_geometry = out.geometry.isna() | out.geometry.is_empty
    if invalid_date.any():
        raise ValueError(
            f"There are {int(invalid_date.sum())} records without a valid date while building sampling_event_id."
        )
    if invalid_geometry.any():
        raise ValueError(
            f"There are {int(invalid_geometry.sum())} records without valid geometry while building sampling_event_id."
        )

    qx = np.rint(out.geometry.x.to_numpy(dtype=float) / coordinate_precision_m).astype(np.int64)
    qy = np.rint(out.geometry.y.to_numpy(dtype=float) / coordinate_precision_m).astype(np.int64)
    date_keys = dates.dt.strftime("%Y-%m-%d")

    if observer_column in out.columns:
        observers = out[observer_column].map(_normalize_observer)
    else:
        observers = pd.Series([None] * len(out), index=out.index, dtype=object)

    if source_row_column in out.columns:
        fallback = out[source_row_column].astype("string")
    elif "obs_id" in out.columns:
        fallback = out["obs_id"].astype("string")
    else:
        fallback = pd.Series(
            [str(position) for position in range(len(out))],
            index=out.index,
            dtype="string",
        )

    observer_keys = pd.Series(index=out.index, dtype="string")
    has_observer = observers.notna()
    observer_keys.loc[has_observer] = observers.loc[has_observer].astype("string")
    observer_keys.loc[~has_observer] = "__missing_observer_row_" + fallback.loc[~has_observer]

    canonical = (
        date_keys.astype("string")
        + "|"
        + observer_keys
        + "|"
        + pd.Series(qx, index=out.index, dtype="int64").astype("string")
        + "|"
        + pd.Series(qy, index=out.index, dtype="int64").astype("string")
    )
    event_ids = canonical.map(
        lambda value: "SE-" + hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:24]
    )

    collision_check = pd.DataFrame({"event_id": event_ids, "canonical": canonical})
    if collision_check.groupby("event_id", observed=True)["canonical"].nunique().gt(1).any():
        raise RuntimeError("An unexpected sampling_event_id hash collision was detected.")

    out["sampling_event_id"] = event_ids.astype("string")
    return out


def sampling_event_summary(frame: pd.DataFrame) -> dict[str, float | int]:
    """Summarize records and events without yet using them as analytical effort."""

    if "sampling_event_id" not in frame.columns:
        raise ValueError("sampling_event_id is required to summarize observation events.")
    ids = frame["sampling_event_id"].dropna().astype("string")
    counts = ids.value_counts()
    n_events = int(ids.nunique())
    n_records = int(len(frame))
    return {
        "n_records": n_records,
        "n_sampling_events": n_events,
        "n_multi_record_events": int((counts > 1).sum()),
        "records_per_event_mean": float(n_records / n_events) if n_events else np.nan,
        "records_per_event_median": float(counts.median()) if n_events else np.nan,
        "records_per_event_max": int(counts.max()) if n_events else 0,
        "event_definition_coordinate_precision_m": float(DEFAULT_EVENT_PRECISION_M),
    }
