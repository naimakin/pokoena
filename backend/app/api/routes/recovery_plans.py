import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import (
    AuthContext,
    get_current_tenant_user,
    get_tenant_scoped_or_404,
    require_project_permission,
    require_scope_access,
)
from app.models.activity import Activity
from app.models.mention import MentionKind
from app.models.project import Project
from app.models.project_scope import ProjectScope
from app.models.recovery_plan import (
    RecoveryItemStatus,
    RecoveryPlan,
    RecoveryPlanItem,
    RecoveryPlanStatus,
)
from app.models.schedule_import import ScheduleImport
from app.models.update_period import UpdatePeriod, UpdatePeriodStatus
from app.models.user import User
from app.models.user_tenant_role import Capability, TenantRole
from app.schemas.activity import MentionableUserOut
from app.schemas.recovery_plan import (
    BulkReviewIn,
    ItemOrderIn,
    PlanReviewIn,
    RecoveryItemCreate,
    RecoveryItemOut,
    RecoveryItemUpdate,
    RecoveryPlanCreate,
    RecoveryPlanDetailOut,
    RecoveryPlanHeaderUpdate,
    RecoveryPlanOut,
    SlipReportOut,
)
from app.services import mitigation
from app.services.mentions import mentionable_users, record_recovery_mentions

router = APIRouter(prefix="/projects/{project_id}/recovery-plan", tags=["recovery-plan"])

# Submit is the one author step that still depends on status: a plan is
# submitted from draft / needs_revision. Editing what the author wrote (root
# cause, action items) is open in every status. It never changes the status;
# the plan records who edited it and when (edited_at), so a reviewer sees an
# edit made after submission or acknowledgement.
_SUBMITTABLE = {RecoveryPlanStatus.draft, RecoveryPlanStatus.needs_revision}
_TRACKING_FIELDS = {"status", "completed_at"}


# --- helpers ---------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _load_plan(db: Session, project_id: uuid.UUID, plan_id: uuid.UUID, ctx: AuthContext) -> RecoveryPlan:
    plan = get_tenant_scoped_or_404(db, RecoveryPlan, plan_id, ctx)
    if plan.project_id != project_id:
        raise HTTPException(status_code=404, detail="Not found")
    return plan


def _is_author_side(plan: RecoveryPlan, ctx: AuthContext) -> bool:
    if ctx.role == TenantRole.subcontractor:
        return plan.project_scope_id is not None and plan.project_scope_id in ctx.scope_ids
    return plan.project_scope_id is None  # company users own self-perform plans


def _require_author(db: Session, plan: RecoveryPlan, ctx: AuthContext) -> None:
    """Who may write a plan's root cause and action items: the same people who
    may start one. The subcontractor whose scope it is, or for self-perform
    work a company user who manages progress (edit_progress)."""
    if not _is_author_side(plan, ctx):
        raise HTTPException(status_code=403, detail="Not the author of this plan")
    if ctx.role != TenantRole.subcontractor:
        require_project_permission(db, plan.project_id, ctx, Capability.edit_progress)


def _can_edit(db: Session, plan: RecoveryPlan, ctx: AuthContext) -> bool:
    try:
        _require_author(db, plan, ctx)
    except HTTPException:
        return False
    return True


def _touch(plan: RecoveryPlan, ctx: AuthContext) -> None:
    plan.edited_at = _now()
    plan.edited_by_user_id = ctx.user.id


def _plan_activity(db: Session, plan: RecoveryPlan, ctx: AuthContext) -> Activity | None:
    """The live activity behind a plan: by row, else by P6 activity ID."""
    if plan.activity_id is not None:
        activity = db.get(Activity, plan.activity_id)
        if activity is not None and activity.tenant_id == ctx.tenant_id:
            return activity
    return (
        db.query(Activity)
        .filter(
            Activity.tenant_id == ctx.tenant_id,
            Activity.project_id == plan.project_id,
            Activity.external_id == plan.activity_external_id,
        )
        .first()
    )


def _owner_name(db: Session, plan: RecoveryPlan, ctx: AuthContext, user_id: uuid.UUID) -> str:
    """An action's owner must be someone who can see the activity."""
    activity = _plan_activity(db, plan, ctx)
    if activity is not None:
        for person in mentionable_users(db, ctx, activity):
            if person.user_id == user_id:
                return person.full_name
    raise HTTPException(status_code=400, detail="That person can't see this activity")


def _edited_after(plan: RecoveryPlan) -> str | None:
    edited = _utc_naive(plan.edited_at)
    if edited is None:
        return None
    if plan.status == RecoveryPlanStatus.accepted and plan.reviewed_at and edited > _utc_naive(plan.reviewed_at):
        return "acknowledgement"
    if plan.status == RecoveryPlanStatus.submitted and plan.submitted_at and edited > _utc_naive(plan.submitted_at):
        return "submission"
    return None


def _decorate(db: Session, plans: list[RecoveryPlan], ctx: AuthContext) -> None:
    user_ids = {
        uid
        for p in plans
        for uid in (p.created_by_user_id, p.submitted_by_user_id, p.reviewed_by_user_id, p.edited_by_user_id)
        if uid is not None
    }
    scope_ids = {p.project_scope_id for p in plans if p.project_scope_id}
    import_ids = {iid for p in plans for iid in (p.from_import_id, p.to_import_id) if iid is not None}
    users = dict(db.query(User.id, User.full_name).filter(User.id.in_(user_ids))) if user_ids else {}
    scopes = (
        dict(db.query(ProjectScope.id, ProjectScope.name).filter(ProjectScope.id.in_(scope_ids)))
        if scope_ids
        else {}
    )
    labels = (
        {
            row.id: row.revision_label or row.filename
            for row in db.query(ScheduleImport.id, ScheduleImport.revision_label, ScheduleImport.filename).filter(
                ScheduleImport.tenant_id == ctx.tenant_id, ScheduleImport.id.in_(import_ids)
            )
        }
        if import_ids
        else {}
    )
    for p in plans:
        p.author_name = users.get(p.created_by_user_id)
        p.submitted_by_name = users.get(p.submitted_by_user_id) if p.submitted_by_user_id else None
        p.reviewed_by_name = users.get(p.reviewed_by_user_id) if p.reviewed_by_user_id else None
        p.edited_by_name = users.get(p.edited_by_user_id) if p.edited_by_user_id else None
        p.scope_name = scopes.get(p.project_scope_id) if p.project_scope_id else None
        p.edited_after = _edited_after(p)
        p.from_label = labels.get(p.from_import_id) if p.from_import_id else None
        p.to_label = labels.get(p.to_import_id) if p.to_import_id else None
        p.can_edit = _can_edit(db, p, ctx)


def _slip_report(db: Session, ctx: AuthContext, project_id: uuid.UUID, **kw) -> dict:
    try:
        return mitigation.build_slip_report(db, ctx.tenant_id, project_id, **kw)
    except mitigation.ComparisonError as err:
        raise HTTPException(status_code=err.status_code, detail=err.detail) from err


# --- slip report ----------------------------------------------------------


@router.get("", response_model=SlipReportOut)
def get_recovery_report(
    project_id: uuid.UUID,
    threshold_days: int = Query(default=1, ge=0, le=60),
    from_import_id: uuid.UUID | None = Query(default=None),
    to_import_id: uuid.UUID | None = Query(default=None),
    from_baseline: bool = Query(default=False),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> SlipReportOut:
    """Slipped activities between two programs. Nothing chosen = the latest
    update against the one before it (or the baseline programme on UPD-1).
    `from_import_id` / `to_import_id` pick programs of this project (404 for any
    other); `from_baseline=true` compares against the active baseline."""
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, Capability.view_delivery, allow_subcontractor=True)

    scope_ids = list(ctx.scope_ids) if ctx.role == TenantRole.subcontractor else None
    result = _slip_report(
        db,
        ctx,
        project_id,
        threshold_days=threshold_days,
        scope_ids=scope_ids,
        from_import_id=from_import_id,
        to_import_id=to_import_id,
        from_baseline=from_baseline,
    )
    return SlipReportOut.model_validate(result)


# --- plan CRUD ----------------------------------------------------------------


def _items(db: Session, plan: RecoveryPlan, ctx: AuthContext) -> list[RecoveryPlanItem]:
    return (
        db.query(RecoveryPlanItem)
        .filter(RecoveryPlanItem.tenant_id == ctx.tenant_id, RecoveryPlanItem.recovery_plan_id == plan.id)
        .order_by(RecoveryPlanItem.order_index, RecoveryPlanItem.created_at)
        .all()
    )


def _detail(db: Session, plan: RecoveryPlan, ctx: AuthContext) -> RecoveryPlanDetailOut:
    _decorate(db, [plan], ctx)
    out = RecoveryPlanDetailOut.model_validate(plan)
    out.items = [RecoveryItemOut.model_validate(i) for i in _items(db, plan, ctx)]
    return out


@router.get("/plans/{plan_id}", response_model=RecoveryPlanDetailOut)
def get_plan(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> RecoveryPlanDetailOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, Capability.view_delivery, allow_subcontractor=True)
    plan = _load_plan(db, project_id, plan_id, ctx)
    if ctx.role == TenantRole.subcontractor:
        require_scope_access(plan.project_scope_id, ctx)
    return _detail(db, plan, ctx)


@router.get("/plans/{plan_id}/people", response_model=list[MentionableUserOut])
def list_plan_people(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    q: str | None = None,
    include_self: bool = False,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> list[MentionableUserOut]:
    """Who can be @-tagged in this plan or own one of its actions: the people
    who can see the activity (services/mentions.mentionable_users). Names and
    roles only, no emails. `include_self` for the owner picker."""
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, Capability.view_delivery, allow_subcontractor=True)
    plan = _load_plan(db, project_id, plan_id, ctx)
    if ctx.role == TenantRole.subcontractor:
        require_scope_access(plan.project_scope_id, ctx)
    activity = _plan_activity(db, plan, ctx)
    if activity is None:
        return []
    needle = (q or "").strip().lower()
    people = [
        m
        for m in mentionable_users(db, ctx, activity)
        if (include_self or m.user_id != ctx.user.id) and (not needle or needle in m.full_name.lower())
    ]
    return [MentionableUserOut(id=m.user_id, full_name=m.full_name, label=m.label) for m in people[:20]]


@router.post("/plans", response_model=RecoveryPlanDetailOut, status_code=201)
def create_plan(
    project_id: uuid.UUID,
    payload: RecoveryPlanCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> RecoveryPlanDetailOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, Capability.view_delivery, allow_subcontractor=True)

    activity = (
        db.query(Activity)
        .filter(
            Activity.tenant_id == ctx.tenant_id,
            Activity.project_id == project_id,
            Activity.external_id == payload.activity_external_id,
        )
        .first()
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")

    if ctx.role == TenantRole.subcontractor:
        require_scope_access(activity.project_scope_id, ctx)
        period = (
            db.query(UpdatePeriod)
            .filter(UpdatePeriod.project_id == project_id, UpdatePeriod.status == UpdatePeriodStatus.open)
            .first()
        )
        if period is None:
            raise HTTPException(status_code=400, detail="No open update period for this project")
    elif ctx.role == TenantRole.company_employee:
        require_project_permission(db, project_id, ctx, Capability.edit_progress)
    elif ctx.role != TenantRole.company_admin:
        raise HTTPException(status_code=403, detail="Not permitted")

    # The plan is raised against the comparison on screen (default when none).
    report = _slip_report(
        db,
        ctx,
        project_id,
        threshold_days=0,
        from_import_id=payload.from_import_id,
        to_import_id=payload.to_import_id,
        from_baseline=payload.from_baseline,
    )
    slip_by_ext = {r["external_id"]: r for r in report["slipped"]}
    slip = slip_by_ext.get(payload.activity_external_id)
    if slip is None:
        raise HTTPException(status_code=400, detail="This activity has not slipped in the current comparison")

    existing = (
        db.query(RecoveryPlan)
        .filter(
            RecoveryPlan.tenant_id == ctx.tenant_id,
            RecoveryPlan.project_id == project_id,
            RecoveryPlan.activity_external_id == payload.activity_external_id,
        )
        .first()
    )
    if existing is not None:
        return _detail(db, existing, ctx)

    open_period = (
        db.query(UpdatePeriod)
        .filter(UpdatePeriod.project_id == project_id, UpdatePeriod.status == UpdatePeriodStatus.open)
        .first()
    )
    plan = RecoveryPlan(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        project_id=project_id,
        activity_external_id=payload.activity_external_id,
        p6_task_id=slip.get("p6_task_id"),
        activity_id=activity.id,
        activity_name=activity.name,
        wbs_path=activity.wbs_path,
        project_scope_id=activity.project_scope_id if ctx.role == TenantRole.subcontractor else None,
        origin_update_period_id=open_period.id if open_period else None,
        from_import_id=report["from_import"].id if report["from_import"] else None,
        to_import_id=report["to_import"].id if report["to_import"] else None,
        slip_days_at_creation=slip["slip_days"],
        status=RecoveryPlanStatus.draft,
        summary=payload.summary,
        created_by_user_id=ctx.user.id,
    )
    db.add(plan)
    db.flush()
    record_recovery_mentions(
        db, ctx, activity, plan, kind=MentionKind.recovery_root_cause, new_text=payload.summary
    )
    db.commit()
    db.refresh(plan)
    return _detail(db, plan, ctx)


@router.patch("/plans/{plan_id}", response_model=RecoveryPlanOut)
def update_plan_header(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    payload: RecoveryPlanHeaderUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> RecoveryPlanOut:
    """The root cause. Editable in every status by the plan's author side; the
    status stays as it is."""
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    plan = _load_plan(db, project_id, plan_id, ctx)
    _require_author(db, plan, ctx)
    if "summary" in payload.model_fields_set and payload.summary != plan.summary:
        before = plan.summary
        plan.summary = payload.summary
        _touch(plan, ctx)
        record_recovery_mentions(
            db, ctx, _plan_activity(db, plan, ctx), plan,
            kind=MentionKind.recovery_root_cause, old_text=before, new_text=payload.summary,
        )
    db.commit()
    db.refresh(plan)
    _decorate(db, [plan], ctx)
    return RecoveryPlanOut.model_validate(plan)


# --- items ------------------------------------------------------------------


def _load_item(db: Session, project_id: uuid.UUID, plan_id: uuid.UUID, item_id: uuid.UUID, ctx: AuthContext):
    item = get_tenant_scoped_or_404(db, RecoveryPlanItem, item_id, ctx)
    if item.project_id != project_id or item.recovery_plan_id != plan_id:
        raise HTTPException(status_code=404, detail="Not found")
    plan = _load_plan(db, project_id, plan_id, ctx)
    return item, plan


@router.post("/plans/{plan_id}/items", response_model=RecoveryItemOut, status_code=201)
def add_item(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    payload: RecoveryItemCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> RecoveryItemOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    plan = _load_plan(db, project_id, plan_id, ctx)
    _require_author(db, plan, ctx)
    owner_name = payload.owner_name
    if payload.owner_user_id is not None:
        owner_name = _owner_name(db, plan, ctx, payload.owner_user_id)

    max_order = (
        db.query(RecoveryPlanItem.order_index)
        .filter(RecoveryPlanItem.recovery_plan_id == plan.id)
        .order_by(RecoveryPlanItem.order_index.desc())
        .first()
    )
    item = RecoveryPlanItem(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        project_id=project_id,
        recovery_plan_id=plan.id,
        order_index=(max_order[0] + 1) if max_order else 0,
        action=payload.action,
        owner_name=owner_name,
        owner_user_id=payload.owner_user_id,
        target_date=payload.target_date,
    )
    db.add(item)
    _touch(plan, ctx)
    db.flush()
    activity = _plan_activity(db, plan, ctx)
    record_recovery_mentions(
        db, ctx, activity, plan, kind=MentionKind.recovery_action, new_text=payload.action, item_id=item.id
    )
    if payload.owner_user_id is not None:
        record_recovery_mentions(
            db, ctx, activity, plan, kind=MentionKind.recovery_owner, item_id=item.id,
            user_ids=[payload.owner_user_id],
        )
    db.commit()
    db.refresh(item)
    return RecoveryItemOut.model_validate(item)


@router.patch("/plans/{plan_id}/items/{item_id}", response_model=RecoveryItemOut)
def update_item(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: RecoveryItemUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> RecoveryItemOut:
    """Any field, in any plan status, for the plan's author side. Ticking an
    action's progress (status / completed_at) is also open, once the plan is
    acknowledged, to the company team and to the subcontractor whose scope it
    is. Only content changes mark the plan as edited."""
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    item, plan = _load_item(db, project_id, plan_id, item_id, ctx)

    changes = payload.model_dump(exclude_unset=True)
    tracking_only = set(changes) <= _TRACKING_FIELDS
    if tracking_only and not _can_edit(db, plan, ctx):
        if plan.status != RecoveryPlanStatus.accepted:
            raise HTTPException(status_code=403, detail="Not the author of this plan")
        if ctx.role == TenantRole.subcontractor:
            require_scope_access(plan.project_scope_id, ctx)
        else:
            require_project_permission(db, project_id, ctx, Capability.edit_progress)
    elif not tracking_only:
        _require_author(db, plan, ctx)

    activity = None
    old_action = item.action
    old_owner = item.owner_user_id
    if "action" in changes and changes["action"] is not None:
        item.action = changes["action"]
    if "owner_user_id" in changes:
        uid = changes["owner_user_id"]
        if uid is None:
            item.owner_user_id = None
            item.owner_name = changes.get("owner_name")
        else:
            item.owner_name = _owner_name(db, plan, ctx, uid)
            item.owner_user_id = uid
    elif "owner_name" in changes:
        item.owner_name = changes["owner_name"] or None
        item.owner_user_id = None
    if "target_date" in changes:
        item.target_date = changes["target_date"]
    if "status" in changes and changes["status"] is not None:
        item.status = RecoveryItemStatus(changes["status"])
    if "completed_at" in changes:
        item.completed_at = changes["completed_at"]

    if not tracking_only:
        _touch(plan, ctx)
        if item.action != old_action:
            activity = _plan_activity(db, plan, ctx)
            record_recovery_mentions(
                db, ctx, activity, plan, kind=MentionKind.recovery_action,
                old_text=old_action, new_text=item.action, item_id=item.id,
            )
        if item.owner_user_id is not None and item.owner_user_id != old_owner:
            activity = activity or _plan_activity(db, plan, ctx)
            record_recovery_mentions(
                db, ctx, activity, plan, kind=MentionKind.recovery_owner, item_id=item.id,
                user_ids=[item.owner_user_id],
            )
    db.commit()
    db.refresh(item)
    return RecoveryItemOut.model_validate(item)


@router.delete("/plans/{plan_id}/items/{item_id}", status_code=204)
def delete_item(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> None:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    item, plan = _load_item(db, project_id, plan_id, item_id, ctx)
    _require_author(db, plan, ctx)
    db.delete(item)
    _touch(plan, ctx)
    db.commit()


@router.put("/plans/{plan_id}/items/order", response_model=list[RecoveryItemOut])
def reorder_items(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    payload: ItemOrderIn,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> list[RecoveryItemOut]:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    plan = _load_plan(db, project_id, plan_id, ctx)
    _require_author(db, plan, ctx)
    items = {i.id: i for i in _items(db, plan, ctx)}
    for idx, item_id in enumerate(payload.ordered_item_ids):
        if item_id in items:
            items[item_id].order_index = idx
    _touch(plan, ctx)
    db.commit()
    ordered = sorted(items.values(), key=lambda i: i.order_index)
    return [RecoveryItemOut.model_validate(i) for i in ordered]


# --- submit / review --------------------------------------------------------


@router.post("/plans/{plan_id}/submit", response_model=RecoveryPlanOut)
def submit_plan(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> RecoveryPlanOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    plan = _load_plan(db, project_id, plan_id, ctx)
    _require_author(db, plan, ctx)
    if plan.status not in _SUBMITTABLE:
        raise HTTPException(status_code=409, detail=f"Plan is already {plan.status.value}")
    item_count = (
        db.query(RecoveryPlanItem).filter(RecoveryPlanItem.recovery_plan_id == plan.id).count()
    )
    if item_count == 0:
        raise HTTPException(status_code=400, detail="Add at least one action item before submitting")

    plan.status = RecoveryPlanStatus.submitted
    plan.submitted_at = _now()
    plan.submitted_by_user_id = ctx.user.id
    db.commit()
    db.refresh(plan)
    _decorate(db, [plan], ctx)
    return RecoveryPlanOut.model_validate(plan)


def _review(plan: RecoveryPlan, decision: str, note: str | None, reviewer_id: uuid.UUID) -> None:
    plan.status = (
        RecoveryPlanStatus.accepted if decision == "accept" else RecoveryPlanStatus.needs_revision
    )
    plan.reviewed_at = _now()
    plan.reviewed_by_user_id = reviewer_id
    plan.review_note = note
    if decision == "accept":
        plan.slip_days_at_review = plan.slip_days_at_creation
    else:
        plan.revision_no += 1


def _wrote(plan: RecoveryPlan, ctx: AuthContext) -> bool:
    """Company admins may acknowledge anything; everyone else not their own plan."""
    if ctx.role == TenantRole.company_admin:
        return False
    return ctx.user.id in (plan.created_by_user_id, plan.submitted_by_user_id)


@router.post("/plans/{plan_id}/review", response_model=RecoveryPlanOut)
def review_plan(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    payload: PlanReviewIn,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> RecoveryPlanOut:
    """Acknowledge a submitted plan ("accept"; "needs_revision" still sends it
    back). Anyone who manages progress on the project may — not just a company
    admin — but never on a plan they wrote themselves."""
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, Capability.edit_progress)
    plan = _load_plan(db, project_id, plan_id, ctx)
    if plan.status != RecoveryPlanStatus.submitted:
        raise HTTPException(status_code=409, detail="Only a submitted plan can be reviewed")
    if _wrote(plan, ctx):
        raise HTTPException(status_code=403, detail="Someone else has to acknowledge your own plan")
    _review(plan, payload.decision, payload.note, ctx.user.id)
    db.commit()
    db.refresh(plan)
    _decorate(db, [plan], ctx)
    return RecoveryPlanOut.model_validate(plan)


@router.post("/plans/bulk-review", response_model=list[RecoveryPlanOut])
def bulk_review(
    project_id: uuid.UUID,
    payload: BulkReviewIn,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> list[RecoveryPlanOut]:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, Capability.edit_progress)
    plans = (
        db.query(RecoveryPlan)
        .filter(
            RecoveryPlan.tenant_id == ctx.tenant_id,
            RecoveryPlan.project_id == project_id,
            RecoveryPlan.id.in_(payload.plan_ids),
            RecoveryPlan.status == RecoveryPlanStatus.submitted,
        )
        .all()
    )
    plans = [p for p in plans if not _wrote(p, ctx)]
    for plan in plans:
        _review(plan, payload.decision, payload.note, ctx.user.id)
    db.commit()
    for plan in plans:
        db.refresh(plan)
    _decorate(db, plans, ctx)
    return [RecoveryPlanOut.model_validate(p) for p in plans]
