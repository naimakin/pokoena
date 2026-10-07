import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import (
    AuthContext,
    get_current_tenant_user,
    get_tenant_scoped_or_404,
    require_project_permission,
    require_role,
)
from app.models.project import Project
from app.models.risk_item import (
    MitigationStatus,
    MitigationStrategy,
    RiskActionItem,
    RiskActionStatus,
    RiskItem,
    RiskStatus,
)
from app.models.user import User
from app.models.user_tenant_role import Capability, TenantRole
from app.services.risk_analysis import pct_to_score
from app.schemas.risk_register import (
    ItemOrderIn,
    MitigationReviewIn,
    RiskActionCreate,
    RiskActionItemOut,
    RiskActionUpdate,
    RiskItemCreate,
    RiskItemDetailOut,
    RiskItemOut,
    RiskItemUpdate,
)

router = APIRouter(prefix="/projects/{project_id}/risks", tags=["risks"])

_MIT_EDITABLE = {MitigationStatus.none, MitigationStatus.draft, MitigationStatus.needs_revision}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_edit(db: Session, project_id: uuid.UUID, ctx: AuthContext) -> None:
    if ctx.role == TenantRole.company_employee:
        require_project_permission(db, project_id, ctx, Capability.edit_risk)
    elif ctx.role != TenantRole.company_admin:
        raise HTTPException(status_code=403, detail="Not permitted")


def _load_risk(db: Session, project_id: uuid.UUID, risk_id: uuid.UUID, ctx: AuthContext) -> RiskItem:
    risk = get_tenant_scoped_or_404(db, RiskItem, risk_id, ctx)
    if risk.project_id != project_id:
        raise HTTPException(status_code=404, detail="Not found")
    return risk


_QSRA_FIELDS = (
    "qsra_enabled", "risk_kind", "probability_pct", "impact_mode", "impact_min", "impact_ml", "impact_max",
    "impact_distribution", "post_probability_pct", "post_impact_min", "post_impact_ml", "post_impact_max",
    "impact_in_schedule", "apply_to_wbs",
)
# Fields where None is a real value ("not entered"), not "leave unchanged".
_QSRA_NULLABLE = {
    "probability_pct", "impact_min", "impact_ml", "impact_max",
    "post_probability_pct", "post_impact_min", "post_impact_ml", "post_impact_max",
}


def _apply_qsra_fields(risk: RiskItem, changes: dict) -> None:
    """The QSRA inputs (see services/risk_analysis.py). A probability entered as
    a % re-derives the 1–5 score, so the matrix and the simulation never
    disagree about how likely a risk is."""
    for field in _QSRA_FIELDS:
        if field not in changes:
            continue
        value = changes[field]
        if value is None and field not in _QSRA_NULLABLE:
            continue
        setattr(risk, field, value)
    if changes.get("probability_pct") is not None:
        risk.probability = pct_to_score(changes["probability_pct"])
    lo, ml, hi = risk.impact_min, risk.impact_ml, risk.impact_max
    present = [v for v in (lo, ml, hi) if v is not None]
    if present != sorted(present):
        raise HTTPException(status_code=422, detail="Impact must satisfy min ≤ most likely ≤ max")


def _decorate(db: Session, risks: list[RiskItem]) -> None:
    ids = [r.id for r in risks]
    counts = (
        dict(
            db.query(RiskActionItem.risk_item_id, func.count(RiskActionItem.id))
            .filter(RiskActionItem.risk_item_id.in_(ids))
            .group_by(RiskActionItem.risk_item_id)
        )
        if ids
        else {}
    )
    user_ids = {r.created_by_user_id for r in risks}
    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}
    for r in risks:
        r.action_item_count = counts.get(r.id, 0)
        u = users.get(r.created_by_user_id)
        r.created_by_name = u.full_name if u else None


@router.get("", response_model=list[RiskItemDetailOut])
def list_risks(
    project_id: uuid.UUID,
    status: RiskStatus | None = Query(default=None),
    embed_items: bool = Query(default=False),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> list[RiskItemDetailOut]:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, Capability.view_risk, Capability.view_reports)

    q = db.query(RiskItem).filter(
        RiskItem.tenant_id == ctx.tenant_id, RiskItem.project_id == project_id
    )
    if status is not None:
        q = q.filter(RiskItem.status == status)
    risks = q.order_by(RiskItem.score.desc(), RiskItem.code).all()
    _decorate(db, risks)

    items_by_risk: dict[uuid.UUID, list[RiskActionItem]] = {}
    if embed_items and risks:
        for item in (
            db.query(RiskActionItem)
            .filter(RiskActionItem.risk_item_id.in_([r.id for r in risks]))
            .order_by(RiskActionItem.order_index, RiskActionItem.created_at)
        ):
            items_by_risk.setdefault(item.risk_item_id, []).append(item)

    out: list[RiskItemDetailOut] = []
    for r in risks:
        d = RiskItemDetailOut.model_validate(r)
        d.items = [RiskActionItemOut.model_validate(i) for i in items_by_risk.get(r.id, [])]
        out.append(d)
    return out


@router.get("/{risk_id}", response_model=RiskItemDetailOut)
def get_risk(
    project_id: uuid.UUID,
    risk_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> RiskItemDetailOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, Capability.view_risk, Capability.view_reports)
    risk = _load_risk(db, project_id, risk_id, ctx)
    _decorate(db, [risk])
    items = (
        db.query(RiskActionItem)
        .filter(RiskActionItem.risk_item_id == risk.id)
        .order_by(RiskActionItem.order_index, RiskActionItem.created_at)
        .all()
    )
    out = RiskItemDetailOut.model_validate(risk)
    out.items = [RiskActionItemOut.model_validate(i) for i in items]
    return out


@router.post("", response_model=RiskItemOut, status_code=201)
def create_risk(
    project_id: uuid.UUID,
    payload: RiskItemCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> RiskItemOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, Capability.view_risk)
    _require_edit(db, project_id, ctx)

    max_n = (
        db.query(func.count(RiskItem.id))
        .filter(RiskItem.tenant_id == ctx.tenant_id, RiskItem.project_id == project_id)
        .scalar()
        or 0
    )
    # count-based numbering can collide if a risk is deleted then re-added; guard.
    existing_codes = {
        c
        for (c,) in db.query(RiskItem.code).filter(
            RiskItem.tenant_id == ctx.tenant_id, RiskItem.project_id == project_id
        )
    }
    n = max_n + 1
    while f"R-{n}" in existing_codes:
        n += 1

    risk = RiskItem(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        project_id=project_id,
        code=f"R-{n}",
        title=payload.title,
        description=payload.description,
        cause=payload.cause,
        effect=payload.effect,
        category=payload.category,
        probability=payload.probability,
        impact=payload.impact,
        score=payload.probability * payload.impact,
        status=RiskStatus(payload.status),
        owner_name=payload.owner_name,
        wbs_path=payload.wbs_path,
        activity_external_ids=payload.activity_external_ids,
        created_by_user_id=ctx.user.id,
    )
    _apply_qsra_fields(risk, payload.model_dump(exclude_unset=True))
    db.add(risk)
    db.commit()
    db.refresh(risk)
    _decorate(db, [risk])
    return RiskItemOut.model_validate(risk)


@router.patch("/{risk_id}", response_model=RiskItemOut)
def update_risk(
    project_id: uuid.UUID,
    risk_id: uuid.UUID,
    payload: RiskItemUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> RiskItemOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, Capability.view_risk)
    _require_edit(db, project_id, ctx)
    risk = _load_risk(db, project_id, risk_id, ctx)

    changes = payload.model_dump(exclude_unset=True)
    mitigation_locked = risk.mitigation_status not in _MIT_EDITABLE
    for field in ("title", "description", "cause", "effect", "category", "owner_name", "wbs_path"):
        if field in changes:
            setattr(risk, field, changes[field])
    if "probability" in changes and changes["probability"] is not None:
        risk.probability = changes["probability"]
        # A new 1–5 likelihood supersedes an older %: the simulation derives
        # it from the score again (and flags it for review) until one is entered.
        if "probability_pct" not in changes:
            risk.probability_pct = None
    if "impact" in changes and changes["impact"] is not None:
        risk.impact = changes["impact"]
    if "status" in changes and changes["status"] is not None:
        risk.status = RiskStatus(changes["status"])
    if "activity_external_ids" in changes and changes["activity_external_ids"] is not None:
        risk.activity_external_ids = changes["activity_external_ids"]
    if "mitigation_strategy" in changes and not mitigation_locked:
        risk.mitigation_strategy = (
            MitigationStrategy(changes["mitigation_strategy"]) if changes["mitigation_strategy"] else None
        )
    if "mitigation_summary" in changes and not mitigation_locked:
        risk.mitigation_summary = changes["mitigation_summary"]
    _apply_qsra_fields(risk, changes)

    risk.score = risk.probability * risk.impact
    db.commit()
    db.refresh(risk)
    _decorate(db, [risk])
    return RiskItemOut.model_validate(risk)


@router.delete("/{risk_id}", status_code=204)
def delete_risk(
    project_id: uuid.UUID,
    risk_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin)),
) -> None:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    risk = _load_risk(db, project_id, risk_id, ctx)
    db.query(RiskActionItem).filter(RiskActionItem.risk_item_id == risk.id).delete()
    db.delete(risk)
    db.commit()


# --- action items ---------------------------------------------------------


def _load_item(db: Session, project_id: uuid.UUID, risk_id: uuid.UUID, item_id: uuid.UUID, ctx: AuthContext):
    item = get_tenant_scoped_or_404(db, RiskActionItem, item_id, ctx)
    if item.project_id != project_id or item.risk_item_id != risk_id:
        raise HTTPException(status_code=404, detail="Not found")
    risk = _load_risk(db, project_id, risk_id, ctx)
    return item, risk


@router.post("/{risk_id}/items", response_model=RiskActionItemOut, status_code=201)
def add_item(
    project_id: uuid.UUID,
    risk_id: uuid.UUID,
    payload: RiskActionCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> RiskActionItemOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, Capability.view_risk)
    _require_edit(db, project_id, ctx)
    risk = _load_risk(db, project_id, risk_id, ctx)
    if risk.mitigation_status not in _MIT_EDITABLE:
        raise HTTPException(status_code=409, detail="Mitigation plan is locked")

    max_order = (
        db.query(RiskActionItem.order_index)
        .filter(RiskActionItem.risk_item_id == risk.id)
        .order_by(RiskActionItem.order_index.desc())
        .first()
    )
    item = RiskActionItem(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        project_id=project_id,
        risk_item_id=risk.id,
        order_index=(max_order[0] + 1) if max_order else 0,
        action=payload.action,
        owner_name=payload.owner_name,
        target_date=payload.target_date,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return RiskActionItemOut.model_validate(item)


@router.patch("/{risk_id}/items/{item_id}", response_model=RiskActionItemOut)
def update_item(
    project_id: uuid.UUID,
    risk_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: RiskActionUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> RiskActionItemOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, Capability.view_risk)
    _require_edit(db, project_id, ctx)
    item, risk = _load_item(db, project_id, risk_id, item_id, ctx)

    changes = payload.model_dump(exclude_unset=True)
    tracking_only = set(changes) <= {"status", "completed_at"}
    if risk.mitigation_status not in _MIT_EDITABLE and not (
        risk.mitigation_status == MitigationStatus.accepted and tracking_only
    ):
        raise HTTPException(status_code=409, detail="Mitigation plan is locked")

    if "action" in changes and changes["action"] is not None:
        item.action = changes["action"]
    if "owner_name" in changes:
        item.owner_name = changes["owner_name"]
    if "target_date" in changes:
        item.target_date = changes["target_date"]
    if "status" in changes and changes["status"] is not None:
        item.status = RiskActionStatus(changes["status"])
    if "completed_at" in changes:
        item.completed_at = changes["completed_at"]
    db.commit()
    db.refresh(item)
    return RiskActionItemOut.model_validate(item)


@router.delete("/{risk_id}/items/{item_id}", status_code=204)
def delete_item(
    project_id: uuid.UUID,
    risk_id: uuid.UUID,
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> None:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, Capability.view_risk)
    _require_edit(db, project_id, ctx)
    item, risk = _load_item(db, project_id, risk_id, item_id, ctx)
    if risk.mitigation_status not in _MIT_EDITABLE:
        raise HTTPException(status_code=409, detail="Mitigation plan is locked")
    db.delete(item)
    db.commit()


@router.put("/{risk_id}/items/order", response_model=list[RiskActionItemOut])
def reorder_items(
    project_id: uuid.UUID,
    risk_id: uuid.UUID,
    payload: ItemOrderIn,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> list[RiskActionItemOut]:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, Capability.view_risk)
    _require_edit(db, project_id, ctx)
    risk = _load_risk(db, project_id, risk_id, ctx)
    items = {
        i.id: i
        for i in db.query(RiskActionItem).filter(RiskActionItem.risk_item_id == risk.id).all()
    }
    for idx, item_id in enumerate(payload.ordered_item_ids):
        if item_id in items:
            items[item_id].order_index = idx
    db.commit()
    return [
        RiskActionItemOut.model_validate(i)
        for i in sorted(items.values(), key=lambda x: x.order_index)
    ]


# --- mitigation submit / review ------------------------------------------


@router.post("/{risk_id}/mitigation/submit", response_model=RiskItemOut)
def submit_mitigation(
    project_id: uuid.UUID,
    risk_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> RiskItemOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, Capability.view_risk)
    _require_edit(db, project_id, ctx)
    risk = _load_risk(db, project_id, risk_id, ctx)

    if risk.mitigation_status not in _MIT_EDITABLE:
        raise HTTPException(status_code=409, detail=f"Already {risk.mitigation_status.value}")
    if risk.mitigation_strategy is None:
        raise HTTPException(status_code=400, detail="Choose a mitigation strategy before submitting")
    if db.query(RiskActionItem).filter(RiskActionItem.risk_item_id == risk.id).count() == 0:
        raise HTTPException(status_code=400, detail="Add at least one action item before submitting")

    risk.mitigation_status = MitigationStatus.submitted
    risk.submitted_at = _now()
    risk.submitted_by_user_id = ctx.user.id
    if risk.status == RiskStatus.open:
        risk.status = RiskStatus.mitigating
    db.commit()
    db.refresh(risk)
    _decorate(db, [risk])
    return RiskItemOut.model_validate(risk)


@router.post("/{risk_id}/mitigation/review", response_model=RiskItemOut)
def review_mitigation(
    project_id: uuid.UUID,
    risk_id: uuid.UUID,
    payload: MitigationReviewIn,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin)),
) -> RiskItemOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    risk = _load_risk(db, project_id, risk_id, ctx)
    if risk.mitigation_status != MitigationStatus.submitted:
        raise HTTPException(status_code=409, detail="Only a submitted plan can be reviewed")

    risk.mitigation_status = (
        MitigationStatus.accepted if payload.decision == "accept" else MitigationStatus.needs_revision
    )
    risk.reviewed_at = _now()
    risk.reviewed_by_user_id = ctx.user.id
    risk.review_note = payload.note
    if payload.decision == "needs_revision":
        risk.revision_no += 1
    db.commit()
    db.refresh(risk)
    _decorate(db, [risk])
    return RiskItemOut.model_validate(risk)
