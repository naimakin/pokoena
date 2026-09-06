"""Baseline-vs-current date-variance engine — pure functions over plain
Python data pre-loaded from Postgres by the caller (app/api/routes/evm.py),
matching every other engine module in this codebase.

Compares each activity's frozen baseline dates (BaselineActivity, captured at
lock time) against its live schedule dates (Activity, reflecting the latest
update-programme .xer import). Variance is measured in calendar days, with a
positive number meaning a slip (later than baseline).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

# Fixed histogram buckets for the finish-variance distribution chart. Each is
# (label, low_inclusive_or_None, high_inclusive_or_None) in calendar days.
_HISTOGRAM_BUCKETS: list[tuple[str, Optional[int], Optional[int]]] = [
    ("30+ days early", None, -31),
    ("1-30 days early", -30, -1),
    ("On baseline", 0, 0),
    ("1-30 days late", 1, 30),
    ("31-90 days late", 31, 90),
    ("90+ days late", 91, None),
]


@dataclass(frozen=True)
class VarianceRow:
    activity_id: str
    external_id: str
    name: str
    wbs_code: Optional[str]
    baseline_start: Optional[date]
    baseline_finish: Optional[date]
    current_start: Optional[date]
    current_finish: Optional[date]
    start_variance_days: Optional[int]
    finish_variance_days: Optional[int]
    is_critical: bool
    status: str
    percent_complete: int


def _day_diff(current: Optional[date], baseline: Optional[date]) -> Optional[int]:
    if current is None or baseline is None:
        return None
    return (current - baseline).days


def _bucket_label(days: Optional[int]) -> Optional[str]:
    if days is None:
        return None
    for label, low, high in _HISTOGRAM_BUCKETS:
        if (low is None or days >= low) and (high is None or days <= high):
            return label
    return None


def compute_baseline_date_variance(baseline_activities: list, activities_by_id: dict) -> dict:
    """`baseline_activities` — BaselineActivity rows (frozen). `activities_by_id`
    — live Activity rows keyed by `id`. Returns a dict with `rows` (list of
    VarianceRow as dicts) and `summary`. Baseline activities whose live
    Activity no longer exists are dropped."""
    rows: list[VarianceRow] = []

    for ba in baseline_activities:
        act = activities_by_id.get(ba.activity_id)
        if act is None:
            # Activity dropped out of the schedule since the baseline was locked.
            continue

        current_start = act.actual_start or act.planned_start or act.early_start
        current_finish = act.actual_finish or act.planned_finish or act.early_finish
        start_var = _day_diff(current_start, ba.baseline_start)
        finish_var = _day_diff(current_finish, ba.baseline_end)

        rows.append(
            VarianceRow(
                activity_id=str(act.id),
                external_id=act.external_id,
                name=act.name,
                wbs_code=ba.wbs_code,
                baseline_start=ba.baseline_start,
                baseline_finish=ba.baseline_end,
                current_start=current_start,
                current_finish=current_finish,
                start_variance_days=start_var,
                finish_variance_days=finish_var,
                is_critical=bool(act.is_critical),
                status=act.status.value if hasattr(act.status, "value") else str(act.status),
                percent_complete=int(act.percent_complete or 0),
            )
        )

    finish_vars = [r.finish_variance_days for r in rows if r.finish_variance_days is not None]
    baseline_finishes = [r.baseline_finish for r in rows if r.baseline_finish is not None]
    current_finishes = [r.current_finish for r in rows if r.current_finish is not None]

    ahead = sum(1 for v in finish_vars if v < 0)
    on_track = sum(1 for v in finish_vars if v == 0)
    behind = sum(1 for v in finish_vars if v > 0)

    baseline_finish = max(baseline_finishes) if baseline_finishes else None
    forecast_finish = max(current_finishes) if current_finishes else None
    project_finish_variance = _day_diff(forecast_finish, baseline_finish)

    histogram = []
    for label, _low, _high in _HISTOGRAM_BUCKETS:
        histogram.append(
            {"label": label, "count": sum(1 for v in finish_vars if _bucket_label(v) == label)}
        )

    summary = {
        "activities_total": len(rows),
        "ahead": ahead,
        "on_track": on_track,
        "behind": behind,
        "baseline_finish": baseline_finish,
        "forecast_finish": forecast_finish,
        "project_finish_variance_days": project_finish_variance,
        "worst_slip_days": max(finish_vars) if finish_vars else None,
        "critical_slip_count": sum(1 for r in rows if r.is_critical and (r.finish_variance_days or 0) > 0),
        "finish_variance_histogram": histogram,
    }

    return {"rows": [r.__dict__ for r in rows], "summary": summary}
