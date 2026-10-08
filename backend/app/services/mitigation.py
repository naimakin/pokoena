"""Recovery Plan services — resolve which two imports to compare, run the slip
diff, and decorate each slipped activity with its recovery-plan status.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.engine.diff.slip_diff import compute_slip_between_snapshots
from app.models.activity import Activity
from app.models.baseline import Baseline, BaselineStatus
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


SlipBasis = Literal["previous_upd", "baseline_programme", "baseline", "custom", "none"]


class ComparisonError(ValueError):
    """A From / To choice the slip report can't honour (routes map it to HTTP)."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class SlipComparison:
    from_import: ScheduleImport | None
    to_import: ScheduleImport | None
    basis: SlipBasis
    # True when the pair is the one the page shows with nothing chosen.
    is_default: bool
    # From = the project's active baseline (Planning > Baselines).
    from_baseline: bool = False
    # Rows to diff against when the baseline's import predates
    # activities_snapshot (built from the frozen baseline_activities).
    from_rows: list[dict] | None = None


def active_baseline(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> Baseline | None:
    return (
        db.query(Baseline)
        .filter(
            Baseline.tenant_id == tenant_id,
            Baseline.project_id == project_id,
            Baseline.status == BaselineStatus.active,
        )
        .first()
    )


def resolve_slip_comparison(
    db: Session,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    from_import_id: uuid.UUID | None = None,
    to_import_id: uuid.UUID | None = None,
    from_baseline: bool = False,
) -> SlipComparison:
    """The pair the Recovery Plan compares. Nothing chosen = exactly the
    default of `resolve_comparison_imports` (latest UPD vs the one before it,
    or the baseline programme on UPD-1). A chosen import must belong to this
    project (404 otherwise, never silently swapped for the default); To alone
    compares against the update before it; From = baseline uses the active
    baseline's program."""
    default_from, default_to, default_basis = resolve_comparison_imports(db, tenant_id, project_id)
    if not (from_import_id or to_import_id or from_baseline):
        return SlipComparison(default_from, default_to, default_basis, is_default=True)
    if from_baseline and from_import_id:
        raise ComparisonError(400, "Choose either a From program or the baseline, not both")

    imports = (
        db.query(ScheduleImport)
        .filter(ScheduleImport.tenant_id == tenant_id, ScheduleImport.project_id == project_id)
        .all()
    )
    by_id = {i.id: i for i in imports}
    for chosen in (from_import_id, to_import_id):
        if chosen is not None and chosen not in by_id:
            raise ComparisonError(404, "Program not found in this project")

    to_import = by_id[to_import_id] if to_import_id else default_to
    if to_import is None:
        return SlipComparison(None, None, "none", is_default=False, from_baseline=from_baseline)

    from_rows: list[dict] | None = None
    basis: SlipBasis = "custom"
    if from_baseline:
        baseline = active_baseline(db, tenant_id, project_id)
        if baseline is None:
            raise ComparisonError(400, "This project has no active baseline")
        from_import = by_id.get(baseline.schedule_import_id)
        if from_import is None or not from_import.activities_snapshot:
            # Imports from before activities_snapshot: compare against the
            # dates frozen on the baseline itself.
            from app.services.schedule_changes import _baseline_frozen_snapshot

            rows, _rels, baseline_import = _baseline_frozen_snapshot(db, tenant_id, project_id)
            from_import = from_import or baseline_import
            from_rows = rows or None
        basis = "baseline"
    elif from_import_id:
        from_import = by_id[from_import_id]
    else:
        earlier = sorted(
            (
                i for i in imports
                if i.revision_no is not None
                and to_import.revision_no is not None
                and i.revision_no < to_import.revision_no
            ),
            key=lambda i: i.revision_no,
        )
        from_import = earlier[-1] if earlier else None

    if from_import is not None and from_import.id == to_import.id:
        raise ComparisonError(
            400,
            "The baseline is this same program; pick a later To program"
            if from_baseline
            else "Pick two different programs to compare",
        )

    is_default = (
        not from_baseline
        and from_import is not None
        and default_from is not None
        and default_to is not None
        and from_import.id == default_from.id
        and to_import.id == default_to.id
    )
    if is_default:
        basis = default_basis
    return SlipComparison(
        from_import, to_import, basis, is_default=is_default, from_baseline=from_baseline, from_rows=from_rows
    )


def _plan_required(row: dict) -> bool:
    """A recovery plan is asked for when the slip is big enough to matter:
    5 days or more, or any slip of a critical activity. A longest-path
    activity that didn't move needs nothing — it used to, and every update
    raised plans nobody needed."""
    slip = row["slip_days"]
    return slip >= _PLAN_REQUIRED_SLIP_DAYS or (bool(row["is_critical"]) and slip >= 1)


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
    from_baseline: bool = False,
) -> dict:
    """Raises ComparisonError for a From / To choice it can't honour."""
    comparison = resolve_slip_comparison(
        db, tenant_id, project_id,
        from_import_id=from_import_id, to_import_id=to_import_id, from_baseline=from_baseline,
    )
    from_import, to_import, basis = comparison.from_import, comparison.to_import, comparison.basis
    from_rows = comparison.from_rows or (from_import.activities_snapshot if from_import else None)
    baseline = active_baseline(db, tenant_id, project_id)
    baseline_import = db.get(ScheduleImport, baseline.schedule_import_id) if baseline else None
    choice = {
        "is_default": comparison.is_default,
        "from_baseline": comparison.from_baseline,
        "baseline": None
        if baseline is None
        else {
            "label": baseline.version_label,
            "import_id": baseline.schedule_import_id,
            "data_date": baseline_import.data_date if baseline_import else None,
        },
    }

    coverage = {
        "from_snapshot": bool(from_rows),
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
            **choice,
            "summary": {
                "slipped_count": 0, "critical_slipped_count": 0, "worst_slip_days": 0,
                "total_added": 0, "total_removed": 0,
                "plans_required": 0, "plans_submitted": 0, "plans_accepted": 0,
            },
            "slipped": [],
        }

    diff = compute_slip_between_snapshots(from_rows, to_import.activities_snapshot, threshold_days=threshold_days)

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
        **choice,
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
