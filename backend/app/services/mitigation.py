"""Recovery Plan services — resolve which two imports to compare, run the slip
diff, and decorate each slipped activity with its recovery-plan status.
"""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.engine.diff.slip_diff import compute_slip_between_snapshots
from app.models.activity import Activity
from app.models.project_scope import ProjectScope
from app.models.recovery_plan import RecoveryPlan, RecoveryPlanItem, RecoveryPlanStatus
from app.models.schedule_import import ScheduleImport

_PLAN_REQUIRED_SLIP_DAYS = 5


def resolve_comparison_imports(
    db: Session,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    from_import_id: uuid.UUID | None = None,
    to_import_id: uuid.UUID | None = None,
) -> tuple[ScheduleImport | None, ScheduleImport | None, Literal["previous_upd", "baseline_programme", "none"]]:
    """`to` = latest numbered UPD, `from` = the one before it. On UPD-1 fall back
    to the baseline-programme import if it carries an activities snapshot."""
    imports = (
        db.query(ScheduleImport)
        .filter(ScheduleImport.tenant_id == tenant_id, ScheduleImport.project_id == project_id)
        .order_by(ScheduleImport.imported_at.desc())
        .all()
    )
    by_id = {i.id: i for i in imports}
    if from_import_id and to_import_id:
        f, t = by_id.get(from_import_id), by_id.get(to_import_id)
        if f and t:
            return f, t, "previous_upd"

    numbered = sorted(
        (i for i in imports if i.revision_no is not None),
        key=lambda i: i.revision_no,
        reverse=True,
    )
    if not numbered:
        return None, None, "none"
    to_import = numbered[0]
    if len(numbered) >= 2:
        return numbered[1], to_import, "previous_upd"

    baseline = next(
        (i for i in sorted(imports, key=lambda i: i.imported_at) if i.revision_no is None and i.activities_snapshot),
        None,
    )
    if baseline is not None:
        return baseline, to_import, "baseline_programme"
    return None, to_import, "none"


def _plan_required(row: dict) -> bool:
    return bool(row["is_critical"]) or bool(row["is_longest_path"]) or row["slip_days"] >= _PLAN_REQUIRED_SLIP_DAYS


def _needs_attention(row: dict, plan: RecoveryPlan | None) -> bool:
    if not _plan_required(row):
        return False
    if plan is None or plan.status != RecoveryPlanStatus.accepted:
        return True
    baseline = plan.slip_days_at_review if plan.slip_days_at_review is not None else row["slip_days"]
    return row["slip_days"] > baseline


def build_slip_report(
    db: Session,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    threshold_days: int = 1,
    scope_ids: list[uuid.UUID] | None = None,
    from_import_id: uuid.UUID | None = None,
    to_import_id: uuid.UUID | None = None,
) -> dict:
    from_import, to_import, basis = resolve_comparison_imports(
        db, tenant_id, project_id, from_import_id=from_import_id, to_import_id=to_import_id
    )

    coverage = {
        "from_snapshot": bool(from_import and from_import.activities_snapshot),
        "to_snapshot": bool(to_import and to_import.activities_snapshot),
    }

    if not (from_import and to_import and coverage["from_snapshot"] and coverage["to_snapshot"]):
        return {
            "project_id": project_id,
            "comparison_basis": "none" if basis == "previous_upd" and not coverage["from_snapshot"] else basis,
            "from_import": from_import,
            "to_import": to_import,
            "threshold_days": threshold_days,
            "coverage": coverage,
            "summary": {
                "slipped_count": 0, "critical_slipped_count": 0, "worst_slip_days": 0,
                "total_added": 0, "total_removed": 0,
                "plans_required": 0, "plans_submitted": 0, "plans_accepted": 0,
            },
            "slipped": [],
        }

    diff = compute_slip_between_snapshots(
        from_import.activities_snapshot, to_import.activities_snapshot, threshold_days=threshold_days
    )

    ext_ids = [r["external_id"] for r in diff["slipped"]]
    activities = (
        db.query(Activity)
        .filter(
            Activity.tenant_id == tenant_id,
            Activity.project_id == project_id,
            Activity.external_id.in_(ext_ids),
        )
        .all()
        if ext_ids
        else []
    )
    act_by_ext = {a.external_id: a for a in activities}
    scope_names = {
        s.id: s.name
        for s in db.query(ProjectScope).filter(
            ProjectScope.tenant_id == tenant_id, ProjectScope.project_id == project_id
        )
    }
    plans = (
        db.query(RecoveryPlan)
        .filter(
            RecoveryPlan.tenant_id == tenant_id,
            RecoveryPlan.project_id == project_id,
            RecoveryPlan.activity_external_id.in_(ext_ids),
        )
        .all()
        if ext_ids
        else []
    )
    plan_by_ext = {p.activity_external_id: p for p in plans}
    item_counts: dict[uuid.UUID, int] = {}
    if plans:
        for pid, cnt in (
            db.query(RecoveryPlanItem.recovery_plan_id, func.count(RecoveryPlanItem.id))
            .filter(RecoveryPlanItem.recovery_plan_id.in_([p.id for p in plans]))
            .group_by(RecoveryPlanItem.recovery_plan_id)
        ):
            item_counts[pid] = cnt

    scope_filter = set(scope_ids) if scope_ids is not None else None
    rows_out: list[dict] = []
    for r in diff["slipped"]:
        act = act_by_ext.get(r["external_id"])
        scope_id = act.project_scope_id if act else None
        if scope_filter is not None and scope_id not in scope_filter:
            continue
        plan = plan_by_ext.get(r["external_id"])
        rows_out.append(
            {
                **r,
                "activity_id": act.id if act else None,
                "scope_id": scope_id,
                "scope_name": scope_names.get(scope_id) if scope_id else None,
                "plan_required": _plan_required(r),
                "needs_attention": _needs_attention(r, plan),
                "plan": None
                if plan is None
                else {
                    "id": plan.id,
                    "status": plan.status.value,
                    "revision_no": plan.revision_no,
                    "item_count": item_counts.get(plan.id, 0),
                    "submitted_at": plan.submitted_at,
                },
            }
        )

    required = [r for r in rows_out if r["plan_required"]]
    plans_submitted = sum(
        1 for r in required if r["plan"] and r["plan"]["status"] in ("submitted", "accepted")
    )
    plans_accepted = sum(1 for r in required if r["plan"] and r["plan"]["status"] == "accepted")

    return {
        "project_id": project_id,
        "comparison_basis": basis,
        "from_import": from_import,
        "to_import": to_import,
        "threshold_days": threshold_days,
        "coverage": coverage,
        "summary": {
            **diff["summary"],
            "slipped_count": len(rows_out),
            "critical_slipped_count": sum(1 for r in rows_out if r["is_critical"] or r["is_longest_path"]),
            "worst_slip_days": max((r["slip_days"] for r in rows_out), default=0),
            "plans_required": len(required),
            "plans_submitted": plans_submitted,
            "plans_accepted": plans_accepted,
        },
        "slipped": rows_out,
    }
