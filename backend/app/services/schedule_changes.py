"""Execution → Changes: compare two schedule imports and report what changed
(activities + logic). Thin wrapper around engine/diff/schedule_diff, reusing
services/mitigation.resolve_comparison_imports for the default From/To pair.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.engine.diff.schedule_diff import compute_schedule_diff
from app.models.activity import Activity
from app.models.baseline import Baseline, BaselineActivity, BaselineStatus
from app.models.schedule_import import ScheduleImport
from app.services.mitigation import resolve_comparison_imports

_EMPTY_REL = {"summary": {"added": 0, "removed": 0, "modified": 0, "total": 0}, "changes": []}


def _baseline_frozen_snapshot(
    db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID
) -> tuple[list[dict] | None, list[dict], ScheduleImport | None]:
    """A synthetic "from" side built from the frozen `baseline_activities` rows,
    for projects whose older imports predate the activities_snapshot column.
    Only dates / WBS survive the freeze — status/%/float/criticality are left
    out so the diff doesn't report them as spurious changes."""
    baseline = (
        db.query(Baseline)
        .filter(
            Baseline.tenant_id == tenant_id,
            Baseline.project_id == project_id,
            Baseline.status == BaselineStatus.active,
        )
        .first()
    )
    if baseline is None:
        return None, [], None
    frozen = db.query(BaselineActivity).filter(BaselineActivity.baseline_id == baseline.id).all()
    if not frozen:
        return None, [], None

    acts = {
        a.id: a
        for a in db.query(Activity).filter(
            Activity.tenant_id == tenant_id,
            Activity.project_id == project_id,
            Activity.id.in_([b.activity_id for b in frozen]),
        )
    }
    snapshot: list[dict] = []
    for b in frozen:
        a = acts.get(b.activity_id)
        if a is None:
            continue
        snapshot.append(
            {
                "external_id": a.external_id,
                "p6_task_id": a.p6_task_id,
                "name": a.name,
                "wbs_path": b.wbs_code or a.wbs_path,
                "planned_start": b.baseline_start.isoformat() if b.baseline_start else None,
                "planned_finish": b.baseline_end.isoformat() if b.baseline_end else None,
            }
        )
    baseline_import = db.get(ScheduleImport, baseline.schedule_import_id)
    rels = baseline_import.relationships_snapshot if baseline_import else []
    return snapshot, list(rels or []), baseline_import


def build_change_report(
    db: Session,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    from_import_id: uuid.UUID | None = None,
    to_import_id: uuid.UUID | None = None,
    date_threshold_days: int = 1,
    duration_threshold_hours: float = 8.0,
    lag_threshold_hours: float = 8.0,
) -> dict:
    from_import, to_import, basis = resolve_comparison_imports(
        db, tenant_id, project_id, from_import_id=from_import_id, to_import_id=to_import_id
    )
    coverage = {
        "from_snapshot": bool(from_import and from_import.activities_snapshot),
        "to_snapshot": bool(to_import and to_import.activities_snapshot),
    }
    # Older snapshots don't carry each activity's calendar day length — the
    # live activities' calendars stand in for them (engine/durations.py).
    hours_per_day_by_ext = dict(
        db.query(Activity.external_id, Activity.hours_per_day).filter(
            Activity.tenant_id == tenant_id, Activity.project_id == project_id
        )
    )
    thresholds = {
        "date_threshold_days": date_threshold_days,
        "duration_threshold_hours": duration_threshold_hours,
        "lag_threshold_hours": lag_threshold_hours,
    }

    if not (from_import and to_import and coverage["from_snapshot"] and coverage["to_snapshot"]):
        # The chosen "from" import has no activity snapshot (it predates the
        # feature). If the "to" side does and a baseline is locked, fall back to
        # comparing against the frozen baseline_activities.
        if to_import and coverage["to_snapshot"] and not from_import_id:
            prev_acts, prev_rels, baseline_import = _baseline_frozen_snapshot(db, tenant_id, project_id)
            if prev_acts:
                diff = compute_schedule_diff(
                    prev_acts,
                    to_import.activities_snapshot,
                    prev_rels,
                    to_import.relationships_snapshot,
                    date_threshold_days=date_threshold_days,
                    duration_threshold_hours=duration_threshold_hours,
                    lag_threshold_hours=lag_threshold_hours,
                    hours_per_day_by_ext=hours_per_day_by_ext,
                )
                return {
                    "project_id": project_id,
                    "comparison_basis": "baseline_frozen",
                    "from_import": baseline_import,
                    "to_import": to_import,
                    "coverage": {"from_snapshot": True, "to_snapshot": True},
                    "thresholds": thresholds,
                    **diff,
                }
        return {
            "project_id": project_id,
            "comparison_basis": "none",
            "from_import": from_import,
            "to_import": to_import,
            "coverage": coverage,
            "thresholds": thresholds,
            "summary": {
                "activities_added": 0, "activities_removed": 0, "activities_renamed": 0,
                "activities_modified": 0, "date_changes": 0, "criticality_changes": 0,
                "relationships_added": 0, "relationships_removed": 0, "relationships_modified": 0,
            },
            "activities": {"added": [], "removed": [], "renamed": [], "modified": []},
            "relationships": _EMPTY_REL,
        }

    diff = compute_schedule_diff(
        from_import.activities_snapshot,
        to_import.activities_snapshot,
        from_import.relationships_snapshot,
        to_import.relationships_snapshot,
        date_threshold_days=date_threshold_days,
        duration_threshold_hours=duration_threshold_hours,
        lag_threshold_hours=lag_threshold_hours,
        hours_per_day_by_ext=hours_per_day_by_ext,
    )
    return {
        "project_id": project_id,
        "comparison_basis": basis,
        "from_import": from_import,
        "to_import": to_import,
        "coverage": coverage,
        "thresholds": thresholds,
        **diff,
    }
