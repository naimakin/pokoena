"""Activity Criticality Score (KS): 0-100, how closely an activity needs watching.

CPM's critical flag is binary — an activity with 8 days of float isn't
critical, however long its lead time or however many trades wait on it. The
score weighs four things instead, as the planning team specified:

    KS = 0.40 S_TF + 0.20 S_D + 0.20 S_FF + 0.20 S_Risk

    S_TF   total float      TF <= 0 -> 100, <= 5d -> 80, <= 15d -> 50, else 20
    S_D    duration share   > 10% of the project -> 100, 5-10% -> 70, < 5% -> 30
    S_FF   free float /     FF = 0 and >= 3 successors -> 100,
           successors       FF = 0 and 1-2 successors -> 70, otherwise 20
    S_Risk site / supply    high -> 100, standard -> 50, low -> 10
                            (not assessed counts as standard)

Bands (traffic light): 80-100 high — daily site follow-up and management
reporting; 50-79 medium — weekly follow-up, early procurement check; 0-49 low —
routine fortnightly / monthly check.

Float is in the activity's own calendar days (engine/durations.py). Duration
share compares calendar-day spans on both sides — the activity's Start->Finish
against the project's earliest Start -> latest Finish — so weekends and
holidays cancel out of the ratio. Completed work, and work without a total
float to go by, gets no score.

Computed on read and attached to the Activity rows as transient attributes
(`criticality_score`, `criticality_breakdown`) for ActivityOut, the same way
routes attach other derived fields — nothing is stored.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.engine.durations import activity_hours_per_day
from app.models.activity import MILESTONE_TYPES, Activity, ActivityStatus
from app.models.activity_relationship import ActivityRelationship
from app.services.schedule_current import get_current_import

SITE_RISK_SCORES = {"high": 100, "standard": 50, "low": 10}
DEFAULT_SITE_RISK = "standard"

W_TOTAL_FLOAT = 0.40
W_DURATION = 0.20
W_FREE_FLOAT = 0.20
W_SITE_RISK = 0.20

_TOL_HOURS = 0.01


def total_float_score(tf_days: float) -> int:
    if tf_days <= 0:
        return 100
    if tf_days <= 5:
        return 80
    if tf_days <= 15:
        return 50
    return 20


def duration_score(share: float) -> int:
    if share > 0.10:
        return 100
    if share >= 0.05:
        return 70
    return 30


def free_float_score(ff_hours: Optional[float], successor_count: int) -> int:
    # No free float on record counts as none: the cautious reading.
    if ff_hours is None or ff_hours <= _TOL_HOURS:
        if successor_count >= 3:
            return 100
        if successor_count >= 1:
            return 70
    return 20


def site_risk_score(site_risk: Optional[str]) -> int:
    return SITE_RISK_SCORES.get(site_risk or DEFAULT_SITE_RISK, SITE_RISK_SCORES[DEFAULT_SITE_RISK])


@dataclass(frozen=True)
class Criticality:
    score: int
    breakdown: dict[str, int]


def _shown_dates(a: Activity) -> tuple[Optional[date], Optional[date]]:
    """The Start/Finish P6 shows (frontend lib/schedule-dates.ts): actual
    once it exists, early (scheduled) before that."""
    planned_start = a.early_start or a.planned_start
    planned_finish = a.early_finish or a.planned_finish
    start = planned_start if a.status == ActivityStatus.not_started else a.actual_start
    finish = a.actual_finish if a.status == ActivityStatus.complete else planned_finish
    return start, finish


def _span_days(start: Optional[date], finish: Optional[date]) -> Optional[int]:
    if start is None or finish is None:
        return None
    return max(0, (finish - start).days) + 1


def activity_span_days(a: Activity) -> float:
    if a.task_type in MILESTONE_TYPES:
        return 0.0
    span = _span_days(*_shown_dates(a))
    if span is not None:
        return float(span)
    return (a.target_duration_hours or 0.0) / activity_hours_per_day(a)


def criticality(a: Activity, project_days: Optional[float], successor_count: int) -> Optional[Criticality]:
    if a.status == ActivityStatus.complete or a.total_float_hours is None:
        return None
    tf_hours = a.total_float_hours
    tf_days = 0.0 if tf_hours <= _TOL_HOURS else tf_hours / activity_hours_per_day(a)
    share = activity_span_days(a) / project_days if project_days and project_days > 0 else 0.0
    breakdown = {
        "total_float": total_float_score(tf_days),
        "duration": duration_score(share),
        "free_float": free_float_score(a.free_float_hours, successor_count),
        "site_risk": site_risk_score(a.site_risk),
    }
    score = (
        W_TOTAL_FLOAT * breakdown["total_float"]
        + W_DURATION * breakdown["duration"]
        + W_FREE_FLOAT * breakdown["free_float"]
        + W_SITE_RISK * breakdown["site_risk"]
    )
    return Criticality(score=round(score), breakdown=breakdown)


def _current_programme(query, db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID):
    """Same rule as GET /activities: activities dropped from the current
    programme don't count toward the project's span."""
    current = get_current_import(db, tenant_id, project_id)
    if current is None:
        return query
    return query.filter((Activity.last_import_id.is_(None)) | (Activity.last_import_id == current.id))


def project_span_days(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> Optional[int]:
    query = db.query(
        func.min(func.coalesce(Activity.actual_start, Activity.early_start, Activity.planned_start)),
        func.max(func.coalesce(Activity.actual_finish, Activity.early_finish, Activity.planned_finish)),
    ).filter(Activity.tenant_id == tenant_id, Activity.project_id == project_id)
    start, finish = _current_programme(query, db, tenant_id, project_id).one()
    return _span_days(start, finish)


def successor_counts(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> dict[uuid.UUID, int]:
    rows = (
        db.query(ActivityRelationship.predecessor_id, func.count(ActivityRelationship.id))
        .filter(ActivityRelationship.tenant_id == tenant_id, ActivityRelationship.project_id == project_id)
        .group_by(ActivityRelationship.predecessor_id)
        .all()
    )
    return {pred_id: count for pred_id, count in rows}


def annotate_criticality(
    db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID, activities: Iterable[Activity]
) -> None:
    """Attach `criticality_score` / `criticality_breakdown` to each row for
    ActivityOut. Two aggregate queries for the whole list."""
    activities = list(activities)
    if not activities:
        return
    project_days = project_span_days(db, tenant_id, project_id)
    successors = successor_counts(db, tenant_id, project_id)
    for a in activities:
        result = criticality(a, project_days, successors.get(a.id, 0))
        a.criticality_score = result.score if result else None
        a.criticality_breakdown = result.breakdown if result else None
