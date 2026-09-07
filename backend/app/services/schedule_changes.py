"""Execution → Changes: compare two schedule imports and report what changed
(activities + logic). Thin wrapper around engine/diff/schedule_diff, reusing
services/mitigation.resolve_comparison_imports for the default From/To pair.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.engine.diff.schedule_diff import compute_schedule_diff
from app.services.mitigation import resolve_comparison_imports

_EMPTY_REL = {"summary": {"added": 0, "removed": 0, "modified": 0, "total": 0}, "changes": []}


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
    thresholds = {
        "date_threshold_days": date_threshold_days,
        "duration_threshold_hours": duration_threshold_hours,
        "lag_threshold_hours": lag_threshold_hours,
    }

    if not (from_import and to_import and coverage["from_snapshot"] and coverage["to_snapshot"]):
        return {
            "project_id": project_id,
            "comparison_basis": "none" if basis == "previous_upd" and not coverage["from_snapshot"] else basis,
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
