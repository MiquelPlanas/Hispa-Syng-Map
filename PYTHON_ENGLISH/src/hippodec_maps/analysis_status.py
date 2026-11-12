"""Common analytical states that keep zero, missingness and non-estimability distinct."""

from __future__ import annotations

from typing import Any

CALCULABLE = "calculable"
INSUFFICIENT_DATA = "insufficient_data"
NOT_ESTIMABLE = "not_estimable"
NOT_AVAILABLE = "not_available"
NOT_APPLICABLE = "not_applicable"

VALID_ANALYSIS_STATUSES = frozenset(
    {CALCULABLE, INSUFFICIENT_DATA, NOT_ESTIMABLE, NOT_AVAILABLE, NOT_APPLICABLE}
)


def analysis_status_record(
    status: str,
    reason: str | None = None,
    **details: Any,
) -> dict[str, Any]:
    """Build a standard record without converting non-calculable states to zero."""

    if status not in VALID_ANALYSIS_STATUSES:
        raise ValueError(f"Unrecognized analytical status: {status}")
    record: dict[str, Any] = {
        "analysis_status": status,
        "analysis_status_reason": reason if reason else None,
    }
    record.update(details)
    return record


def is_calculable(status: object) -> bool:
    return str(status) == CALCULABLE
