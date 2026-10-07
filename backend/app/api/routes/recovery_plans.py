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
    require_role,
    require_scope_access,
)
from app.models.activity import Activity
from app.models.project import Project
from app.models.project_scope import ProjectScope
from app.models.recovery_plan import (
    RecoveryItemStatus,
    RecoveryPlan,
    RecoveryPlanItem,
    RecoveryPlanStatus,
)
from app.models.update_period import UpdatePeriod, UpdatePeriodStatus
from app.models.user import User
from app.models.user_tenant_role import Capability, TenantRole
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

router = APIRouter(prefix="/projects/{project_id}/recovery-plan", tags=["recovery-plan"])

_EDITABLE = {RecoveryPlanStatus.draft, RecoveryPlanStatus.needs_revision}


# --- helpers ---------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_plan(db: Session, project_id: uuid.UUID, plan_id: uuid.UUID, ctx: AuthContext) -> RecoveryPlan:
    plan = get_tenant_scoped_or_404(db, RecoveryPlan, plan_id, ctx)
    if plan.project_id != project_id:
        raise HTTPException(status_code=404, detail="Not found")
    return plan


def _is_author_side(plan: RecoveryPlan, ctx: AuthContext) -> bool:
    if ctx.role == TenantRole.subcontractor:
        return plan.project_scope_id is not None and plan.project_scope_id in ctx.scope_ids
    return plan.project_scope_id is None  # company users own self-perform plans


def _require_author_editable(plan: RecoveryPlan, ctx: AuthContext) -> None:
    if not _is_author_side(plan, ctx):
        raise HTTPException(status_code=403, detail="Not the author of this plan")
    if plan.status not in _EDITABLE:
        raise HTTPException(status_code=409, detail=f"Plan is {plan.status.value} and can't be edited")


def _decorate(db: Session, plans: list[RecoveryPlan], ctx: AuthContext) -> None:
    user_ids = {p.created_by_user_id for p in plans}
    scope_ids = {p.project_scope_id for p in plans if p.project_scope_id}
    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}
    scopes = (
        {s.id: s for s in db.query(ProjectScope).filter(ProjectScope.id.in_(scope_ids)).all()}
        if scope_ids
        else {}
    )
    for p in plans:
        u = users.get(p.created_by_user_id)
        p.author_name = u.full_name if u else None
        s = scopes.get(p.project_scope_id) if p.project_scope_id else None
        p.scope_name = s.name if s else None


# --- slip report ----------------------------------------------------------


@router.get("", response_model=SlipReportOut)
def get_recovery_report(
    project_id: uuid.UUID,
    threshold_days: int = Query(default=1, ge=0, le=60),
    from_import_id: uuid.UUID | None = Query(default=None),
    to_import_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> SlipReportOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, Capability.view_delivery, allow_subcontractor=True)

    scope_ids = list(ctx.scope_ids) if ctx.role == TenantRole.subcontractor else None
    result = mitigation.build_slip_report(
        db,
        ctx.tenant_id,
        project_id,
        threshold_days=threshold_days,
        scope_ids=scope_ids,
        from_import_id=from_import_id,
        to_import_id=to_import_id,
    )
    return SlipReportOut.model_validate(result)


# --- plan CRUD ----------------------------------------------------------------


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
    _decorate(db, [plan], ctx)
    items = (
        db.query(RecoveryPlanItem)
        .filter(RecoveryPlanItem.recovery_plan_id == plan.id)
        .order_by(RecoveryPlanItem.order_index, RecoveryPlanItem.created_at)
        .all()
    )
    out = RecoveryPlanDetailOut.model_validate(plan)
    out.items = [RecoveryItemOut.model_validate(i) for i in items]
    return out


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

    report = mitigation.build_slip_report(db, ctx.tenant_id, project_id, threshold_days=0)
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
        _decorate(db, [existing], ctx)
        out = RecoveryPlanDetailOut.model_validate(existing)
        out.items = []
        return out

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
    db.commit()
    db.refresh(plan)
    _decorate(db, [plan], ctx)
    out = RecoveryPlanDetailOut.model_validate(plan)
    out.items = []
    return out


@router.patch("/plans/{plan_id}", response_model=RecoveryPlanOut)
def update_plan_header(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    payload: RecoveryPlanHeaderUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> RecoveryPlanOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    plan = _load_plan(db, project_id, plan_id, ctx)
    _require_author_editable(plan, ctx)
    if "summary" in payload.model_dump(exclude_unset=True):
        plan.summary = payload.summary
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
    _require_author_editable(plan, ctx)

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
        owner_name=payload.owner_name,
        target_date=payload.target_date,
    )
    db.add(item)
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
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    item, plan = _load_item(db, project_id, plan_id, item_id, ctx)

    changes = payload.model_dump(exclude_unset=True)
    tracking_only = set(changes) <= {"status", "completed_at"}
    if plan.status == RecoveryPlanStatus.accepted and tracking_only:
        # Progress tracking on an accepted plan — company users + own-scope sub.
        if ctx.role == TenantRole.subcontractor:
            require_scope_access(plan.project_scope_id, ctx)
    else:
        _require_author_editable(plan, ctx)

    if "action" in changes and changes["action"] is not None:
        item.action = changes["action"]
    if "owner_name" in changes:
        item.owner_name = changes["owner_name"]
    if "target_date" in changes:
        item.target_date = changes["target_date"]
    if "status" in changes and changes["status"] is not None:
        item.status = RecoveryItemStatus(changes["status"])
    if "completed_at" in changes:
        item.completed_at = changes["completed_at"]
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
    _require_author_editable(plan, ctx)
    db.delete(item)
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
    _require_author_editable(plan, ctx)
    items = {
        i.id: i
        for i in db.query(RecoveryPlanItem).filter(RecoveryPlanItem.recovery_plan_id == plan.id).all()
    }
    for idx, item_id in enumerate(payload.ordered_item_ids):
        if item_id in items:
            items[item_id].order_index = idx
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
    if not _is_author_side(plan, ctx):
        raise HTTPException(status_code=403, detail="Not the author of this plan")
    if plan.status not in _EDITABLE:
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


@router.post("/plans/{plan_id}/review", response_model=RecoveryPlanOut)
def review_plan(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    payload: PlanReviewIn,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin)),
) -> RecoveryPlanOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    plan = _load_plan(db, project_id, plan_id, ctx)
    if plan.status != RecoveryPlanStatus.submitted:
        raise HTTPException(status_code=409, detail="Only a submitted plan can be reviewed")
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
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin)),
) -> list[RecoveryPlanOut]:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
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
    for plan in plans:
        _review(plan, payload.decision, payload.note, ctx.user.id)
    db.commit()
    for plan in plans:
        db.refresh(plan)
    _decorate(db, plans, ctx)
    return [RecoveryPlanOut.model_validate(p) for p in plans]
