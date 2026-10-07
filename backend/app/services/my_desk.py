"""Execution → My Desk: one user's personal layer over the shared schedule.

Three reads, all across every project the caller can see (or one of them):

- `build_inbox` — what's waiting on the caller, rolled up from the approval
  queues that already exist (recovery plans, flag reviews, mitigation plans,
  open update periods). No table of its own.
- `build_pins` — the activities the caller pinned, against the live programme:
  drift since pinning, and the import before the current one ("since UPD-n").
- `build_suggestions` — what to pin on an empty desk: incomplete activities
  with negative float, on the longest/critical path, or starting soon.

Pins and notes are private: RLS isolates the tenant, and every query here also
filters on the caller's user_id.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func, true
from sqlalchemy.orm import Session

from app.deps import AuthContext, has_capability
from app.models.activity import Activity, ActivityStatus
from app.models.mention import Mention
from app.models.my_desk import ActivityPin, PersonalNote
from app.models.project import Project
from app.models.project_scope import ProjectScope
from app.models.recovery_plan import RecoveryPlan, RecoveryPlanStatus
from app.models.risk_item import MitigationStatus, RiskItem
from app.models.schedule_import import ScheduleImport
from app.models.scope_submission import ScopeSubmission
from app.models.update_period import UpdatePeriod, UpdatePeriodStatus
from app.models.user_tenant_role import Capability, TenantRole
from app.schemas.activity import ActivityOut
from app.schemas.my_desk import InboxItemOut, NoteOut, PinOut, SuggestionOut
from app.services.criticality import annotate_criticality, shown_dates
from app.services.schedule_current import get_current_import, to_naive

_SUGGESTION_LIMIT = 5
_SOON_DAYS = 14
_DUE_SOON = timedelta(days=3)
_TONE_ORDER = {"crit": 0, "warn": 1, "info": 2}


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _names(labels: list[str], limit: int = 3) -> str:
    shown = ", ".join(labels[:limit])
    extra = len(labels) - limit
    return f"{shown} +{extra} more" if extra > 0 else shown


def current_programme(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID):
    """The current import and a filter for the activities in it — the same rule
    as GET /activities (a row dropped from the programme is kept but not live)."""
    current = get_current_import(db, tenant_id, project_id)
    if current is None:
        return None, true()
    return current, (Activity.last_import_id.is_(None)) | (Activity.last_import_id == current.id)


# ---------------------------------------------------------------- inbox


def build_inbox(db: Session, ctx: AuthContext, projects: list[Project]) -> list[InboxItemOut]:
    if not projects:
        return []
    by_id = {p.id: p for p in projects}
    ids = list(by_id)
    is_admin = ctx.role == TenantRole.company_admin
    me = ctx.user.id
    items: list[InboxItemOut] = []

    def add(kind, project_id, title, *, detail=None, count=1, due_at=None, tone="info", href):
        p = by_id[project_id]
        items.append(
            InboxItemOut(
                kind=kind, project_id=p.id, project_code=p.code, project_name=p.name, title=title,
                detail=detail, count=count, due_at=due_at, tone=tone, href=href,
            )
        )

    # Recovery plans: admins review submitted ones; authors fix the ones sent back.
    plans = (
        db.query(RecoveryPlan)
        .filter(
            RecoveryPlan.tenant_id == ctx.tenant_id,
            RecoveryPlan.project_id.in_(ids),
            RecoveryPlan.status.in_([RecoveryPlanStatus.submitted, RecoveryPlanStatus.needs_revision]),
        )
        .order_by(RecoveryPlan.activity_external_id)
        .all()
    )
    can_ack = has_capability(ctx, Capability.edit_progress)
    review: dict[uuid.UUID, list[str]] = defaultdict(list)
    revise: dict[uuid.UUID, list[str]] = defaultdict(list)
    for plan in plans:
        wrote = me in (plan.created_by_user_id, plan.submitted_by_user_id)
        if plan.status == RecoveryPlanStatus.submitted and (is_admin or (can_ack and not wrote)):
            review[plan.project_id].append(plan.activity_external_id)
        elif plan.status == RecoveryPlanStatus.needs_revision and me in (plan.created_by_user_id, plan.submitted_by_user_id):
            revise[plan.project_id].append(plan.activity_external_id)
    for pid, codes in review.items():
        add("recovery_review", pid, f"{_plural(len(codes), 'recovery plan')} to acknowledge",
            detail=_names(codes), count=len(codes), tone="warn", href="/recovery-plan")
    for pid, codes in revise.items():
        add("recovery_revision", pid, f"{_plural(len(codes), 'recovery plan')} sent back for revision",
            detail=_names(codes), count=len(codes), tone="warn", href="/recovery-plan")

    # People who tagged the caller in an activity comment.
    for pid, n in (
        db.query(Mention.project_id, func.count(Mention.id))
        .filter(
            Mention.tenant_id == ctx.tenant_id,
            Mention.mentioned_user_id == me,
            Mention.read_at.is_(None),
            Mention.project_id.in_(ids),
        )
        .group_by(Mention.project_id)
        .all()
    ):
        add("mention", pid, f"{_plural(n, 'new mention')}", count=n, tone="info", href="/execution/my-desk#mentions")

    # Mitigation plans on the risk register: same review loop as recovery plans.
    risks = (
        db.query(RiskItem)
        .filter(
            RiskItem.tenant_id == ctx.tenant_id,
            RiskItem.project_id.in_(ids),
            RiskItem.mitigation_status.in_([MitigationStatus.submitted, MitigationStatus.needs_revision]),
        )
        .order_by(RiskItem.code)
        .all()
    )
    risk_review: dict[uuid.UUID, list[str]] = defaultdict(list)
    risk_revise: dict[uuid.UUID, list[str]] = defaultdict(list)
    for risk in risks:
        if risk.mitigation_status == MitigationStatus.submitted and is_admin:
            risk_review[risk.project_id].append(risk.code)
        elif risk.mitigation_status == MitigationStatus.needs_revision and me in (
            risk.created_by_user_id, risk.submitted_by_user_id
        ):
            risk_revise[risk.project_id].append(risk.code)
    for pid, codes in risk_review.items():
        add("mitigation_review", pid, f"{_plural(len(codes), 'mitigation plan')} awaiting your review",
            detail=_names(codes), count=len(codes), tone="warn", href="/risk/mitigation-plans")
    for pid, codes in risk_revise.items():
        add("mitigation_revision", pid, f"{_plural(len(codes), 'mitigation plan')} sent back for revision",
            detail=_names(codes), count=len(codes), tone="warn", href="/risk/mitigation-plans")

    # Open update periods: the deadline, and which subcontractors still owe an update.
    periods = (
        db.query(UpdatePeriod)
        .filter(
            UpdatePeriod.tenant_id == ctx.tenant_id,
            UpdatePeriod.project_id.in_(ids),
            UpdatePeriod.status == UpdatePeriodStatus.open,
        )
        .all()
    )
    if periods:
        expected: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
        for pid, org_id in (
            db.query(ProjectScope.project_id, ProjectScope.subcontractor_org_id)
            .filter(
                ProjectScope.tenant_id == ctx.tenant_id,
                ProjectScope.project_id.in_([p.project_id for p in periods]),
                ProjectScope.subcontractor_org_id.isnot(None),
            )
            .all()
        ):
            expected[pid].add(org_id)
        submitted: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
        for period_id, org_id in (
            db.query(ScopeSubmission.update_period_id, ScopeSubmission.subcontractor_org_id)
            .filter(
                ScopeSubmission.tenant_id == ctx.tenant_id,
                ScopeSubmission.update_period_id.in_([p.id for p in periods]),
            )
            .all()
        ):
            submitted[period_id].add(org_id)

        now = datetime.utcnow()
        for period in periods:
            deadline = to_naive(period.deadline_at)
            owed = len(expected[period.project_id] - submitted[period.id])
            total = len(expected[period.project_id])
            if deadline is not None and deadline < now:
                title, tone = f"{period.label} is past its deadline", "crit"
            else:
                title = f"{period.label} is open"
                tone = "warn" if deadline is not None and deadline - now <= _DUE_SOON else "info"
            detail = (
                f"{owed} of {total} subcontractors haven't submitted" if owed
                else "Every subcontractor has submitted" if total
                else None
            )
            add("update_period", period.project_id, title, detail=detail, due_at=deadline, tone=tone,
                href="/dashboard")

    items.sort(key=lambda i: (_TONE_ORDER[i.tone], i.due_at or datetime.max, i.project_code, i.kind))
    return items


# ---------------------------------------------------------------- pins


def _previous_import(db: Session, current: ScheduleImport) -> tuple[str | None, dict[str, dict]]:
    """The import before the current one: its label and its snapshot by
    activity ID. Only that one blob is read."""
    prev = (
        db.query(ScheduleImport.id, ScheduleImport.revision_label, ScheduleImport.filename)
        .filter(
            ScheduleImport.tenant_id == current.tenant_id,
            ScheduleImport.project_id == current.project_id,
            ScheduleImport.id != current.id,
            ScheduleImport.imported_at < current.imported_at,
        )
        .order_by(ScheduleImport.imported_at.desc())
        .first()
    )
    if prev is None:
        return None, {}
    snapshot = db.query(ScheduleImport.activities_snapshot).filter(ScheduleImport.id == prev.id).scalar() or []
    return prev.revision_label or prev.filename, {row["external_id"]: row for row in snapshot if row.get("external_id")}


def _snap_finish(row: dict) -> date | None:
    """Shown finish from a snapshot row — the rule of criticality.shown_dates."""
    raw = row.get("actual_finish") if row.get("status") == ActivityStatus.complete.value else (
        row.get("early_finish") or row.get("planned_finish")
    )
    return date.fromisoformat(raw) if raw else None


def build_pins(db: Session, ctx: AuthContext, pins: list[ActivityPin], projects: dict[uuid.UUID, Project]) -> list[PinOut]:
    out: list[PinOut] = []
    by_project: dict[uuid.UUID, list[ActivityPin]] = defaultdict(list)
    for pin in pins:
        if pin.project_id in projects:
            by_project[pin.project_id].append(pin)

    for project_id, project_pins in by_project.items():
        project = projects[project_id]
        codes = [p.activity_external_id for p in project_pins]
        current, live = current_programme(db, ctx.tenant_id, project_id)
        activities = (
            db.query(Activity)
            .filter(Activity.tenant_id == ctx.tenant_id, Activity.project_id == project_id,
                    Activity.external_id.in_(codes), live)
            .all()
        )
        annotate_criticality(db, ctx.tenant_id, project_id, activities)
        by_code = {a.external_id: a for a in activities}
        prev_label, prev_rows = _previous_import(db, current) if current is not None else (None, {})
        note_counts = dict(
            db.query(PersonalNote.activity_external_id, func.count(PersonalNote.id))
            .filter(
                PersonalNote.tenant_id == ctx.tenant_id,
                PersonalNote.user_id == ctx.user.id,
                PersonalNote.project_id == project_id,
                PersonalNote.activity_external_id.in_(codes),
            )
            .group_by(PersonalNote.activity_external_id)
            .all()
        )

        for pin in project_pins:
            activity = by_code.get(pin.activity_external_id)
            finish = shown_dates(activity)[1] if activity is not None else None
            prev = prev_rows.get(pin.activity_external_id)
            out.append(
                PinOut(
                    id=pin.id,
                    project_id=project.id,
                    project_code=project.code,
                    project_name=project.name,
                    activity_external_id=pin.activity_external_id,
                    activity_name=activity.name if activity is not None else pin.activity_name,
                    pinned_at=pin.created_at,
                    pinned_finish=pin.pinned_finish,
                    pinned_total_float_hours=pin.pinned_total_float_hours,
                    pinned_hours_per_day=pin.pinned_hours_per_day,
                    pinned_revision_label=pin.pinned_revision_label,
                    activity=ActivityOut.model_validate(activity) if activity is not None else None,
                    finish=finish,
                    drift_days=(finish - pin.pinned_finish).days if finish and pin.pinned_finish else None,
                    previous_revision_label=prev_label if prev is not None else None,
                    previous_finish=_snap_finish(prev) if prev is not None else None,
                    previous_total_float_hours=prev.get("total_float_hours") if prev is not None else None,
                    note_count=note_counts.get(pin.activity_external_id, 0),
                )
            )

    out.sort(key=lambda p: p.pinned_at, reverse=True)
    return out


def pin_snapshot(db: Session, activity: Activity) -> dict:
    """The activity as it stands now — frozen on a pin or a note."""
    current = get_current_import(db, activity.tenant_id, activity.project_id)
    return {
        "finish": shown_dates(activity)[1],
        "total_float_hours": activity.total_float_hours,
        "hours_per_day": activity.hours_per_day,
        "revision_label": (current.revision_label or current.filename) if current is not None else None,
    }


# ---------------------------------------------------------------- suggestions


def _suggestion_reason(a: Activity, data_date: date) -> str | None:
    tf = a.total_float_hours
    if tf is not None and tf < 0:
        return "Negative float"
    if a.is_longest_path:
        return "On the longest path"
    if a.is_critical:
        return "Critical"
    start = shown_dates(a)[0]
    if a.status == ActivityStatus.not_started and start is not None and 0 <= (start - data_date).days <= _SOON_DAYS:
        return f"Starts within {_SOON_DAYS} days"
    return None


def build_suggestions(db: Session, ctx: AuthContext, project: Project) -> list[SuggestionOut]:
    current, live = current_programme(db, ctx.tenant_id, project.id)
    pinned = {
        code
        for (code,) in db.query(ActivityPin.activity_external_id).filter(
            ActivityPin.tenant_id == ctx.tenant_id,
            ActivityPin.user_id == ctx.user.id,
            ActivityPin.project_id == project.id,
        )
    }
    activities = (
        db.query(Activity)
        .filter(Activity.tenant_id == ctx.tenant_id, Activity.project_id == project.id,
                Activity.status != ActivityStatus.complete, live)
        .all()
    )
    data_date = (
        to_naive(current.data_date).date() if current is not None and current.data_date is not None else date.today()
    )
    candidates = []
    for a in activities:
        if a.external_id in pinned:
            continue
        reason = _suggestion_reason(a, data_date)
        if reason is not None:
            candidates.append((a, reason))
    annotate_criticality(db, ctx.tenant_id, project.id, [a for a, _ in candidates])
    candidates.sort(
        key=lambda c: (
            -(c[0].criticality_score or 0),
            c[0].total_float_hours if c[0].total_float_hours is not None else float("inf"),
            c[0].external_id,
        )
    )
    return [SuggestionOut(activity=ActivityOut.model_validate(a), reason=r) for a, r in candidates[:_SUGGESTION_LIMIT]]


# ---------------------------------------------------------------- notes


def note_out(note: PersonalNote, projects: dict[uuid.UUID, Project]) -> NoteOut:
    out = NoteOut.model_validate(note)
    if note.project_id is not None and note.project_id in projects:
        out.project_code = projects[note.project_id].code
    return out


def sort_notes(notes: list[PersonalNote]) -> list[PersonalNote]:
    """Open before done; among open ones, reminders by date first, then newest."""

    def key(n: PersonalNote):
        return (
            n.done_at is not None,
            n.remind_on is None,
            n.remind_on or date.max,
            -(n.created_at.timestamp() if n.created_at else 0),
        )

    return sorted(notes, key=key)
