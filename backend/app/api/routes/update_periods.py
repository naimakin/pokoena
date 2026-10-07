import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.notifications import send_reminder_email
from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_role
from app.models.project import Project
from app.models.scope_submission import ScopeSubmission
from app.models.update_period import UpdatePeriod, UpdatePeriodStatus
from app.models.user import User
from app.models.user_tenant_role import TenantRole, UserTenantRole
from app.schemas.update_period import UpdatePeriodCreate, UpdatePeriodOut

router = APIRouter(prefix="/update-periods", tags=["update-periods"])


@router.get("", response_model=list[UpdatePeriodOut])
def list_update_periods(
    project_id: uuid.UUID, db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)
) -> list[UpdatePeriod]:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    return (
        db.query(UpdatePeriod)
        .filter(UpdatePeriod.tenant_id == ctx.tenant_id, UpdatePeriod.project_id == project_id)
        .order_by(UpdatePeriod.period_number.desc())
        .all()
    )


@router.post("", response_model=UpdatePeriodOut, status_code=status.HTTP_201_CREATED)
def open_update_period(
    payload: UpdatePeriodCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin)),
) -> UpdatePeriod:
    """Opens the window in which subcontractors update progress on their
    scopes. One open period per project at a time."""
    get_tenant_scoped_or_404(db, Project, payload.project_id, ctx)
    periods = (
        db.query(UpdatePeriod)
        .filter(UpdatePeriod.tenant_id == ctx.tenant_id, UpdatePeriod.project_id == payload.project_id)
        .all()
    )
    if any(p.status == UpdatePeriodStatus.open for p in periods):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This project already has an open update period — close it first"
        )
    now = datetime.now(timezone.utc)
    opens_at = payload.opens_at or now
    deadline_at = payload.deadline_at if payload.deadline_at.tzinfo else payload.deadline_at.replace(tzinfo=timezone.utc)
    if deadline_at <= now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The deadline must be in the future")
    number = payload.period_number or max((p.period_number for p in periods), default=0) + 1
    period = UpdatePeriod(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        project_id=payload.project_id,
        period_number=number,
        label=(payload.label or "").strip() or f"Update {number}",
        opens_at=opens_at,
        deadline_at=deadline_at,
        status=UpdatePeriodStatus.open,
    )
    db.add(period)
    db.commit()
    db.refresh(period)
    return period


@router.post("/{period_id}/close", response_model=UpdatePeriodOut)
def close_update_period(
    period_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin)),
) -> UpdatePeriod:
    period = get_tenant_scoped_or_404(db, UpdatePeriod, period_id, ctx)
    period.status = UpdatePeriodStatus.closed
    period.closed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(period)
    return period


@router.post("/{period_id}/submit", response_model=UpdatePeriodOut)
def submit_scope(
    period_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.subcontractor)),
) -> UpdatePeriod:
    period = get_tenant_scoped_or_404(db, UpdatePeriod, period_id, ctx)
    if period.status != UpdatePeriodStatus.open:
        raise HTTPException(status_code=400, detail="Update period is not open")
    if not ctx.subcontractor_org_id:
        raise HTTPException(status_code=400, detail="User has no assigned subcontractor organization")

    existing = (
        db.query(ScopeSubmission)
        .filter(
            ScopeSubmission.update_period_id == period_id,
            ScopeSubmission.subcontractor_org_id == ctx.subcontractor_org_id,
        )
        .first()
    )
    if not existing:
        db.add(
            ScopeSubmission(
                id=uuid.uuid4(),
                tenant_id=ctx.tenant_id,
                update_period_id=period_id,
                subcontractor_org_id=ctx.subcontractor_org_id,
                submitted_by_user_id=ctx.user.id,
            )
        )
        db.commit()
    return period


@router.post("/{period_id}/remind")
def remind_non_responders(
    period_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_role(TenantRole.company_admin)),
) -> dict:
    period = get_tenant_scoped_or_404(db, UpdatePeriod, period_id, ctx)

    submitted_org_ids = {
        row.subcontractor_org_id
        for row in db.query(ScopeSubmission)
        .filter(ScopeSubmission.update_period_id == period_id)
        .all()
    }

    query = (
        db.query(User, UserTenantRole)
        .join(UserTenantRole, UserTenantRole.user_id == User.id)
        .filter(
            UserTenantRole.tenant_id == ctx.tenant_id,
            UserTenantRole.role == TenantRole.subcontractor,
            UserTenantRole.is_active.is_(True),
            UserTenantRole.subcontractor_org_id.isnot(None),
        )
    )
    if submitted_org_ids:
        query = query.filter(~UserTenantRole.subcontractor_org_id.in_(submitted_org_ids))
    non_responders = query.all()

    for user, _membership in non_responders:
        send_reminder_email(
            user.email,
            f"Reminder: {period.label} closes soon",
            f"Please submit your scope updates for {period.label}.",
        )

    return {"reminded": len(non_responders)}
