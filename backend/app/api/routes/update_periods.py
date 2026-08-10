import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.notifications import send_reminder_email
from app.db.session import get_db
from app.deps import get_current_user, require_roles
from app.models.scope_submission import ScopeSubmission
from app.models.update_period import UpdatePeriod, UpdatePeriodStatus
from app.models.user import User, UserRole
from app.schemas.update_period import UpdatePeriodCreate, UpdatePeriodOut

router = APIRouter(prefix="/update-periods", tags=["update-periods"])


@router.get("", response_model=list[UpdatePeriodOut])
def list_update_periods(
    project_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(get_current_user)
) -> list[UpdatePeriod]:
    return (
        db.query(UpdatePeriod)
        .filter(UpdatePeriod.project_id == project_id)
        .order_by(UpdatePeriod.period_number.desc())
        .all()
    )


@router.post("", response_model=UpdatePeriodOut, status_code=status.HTTP_201_CREATED)
def open_update_period(
    payload: UpdatePeriodCreate, db: Session = Depends(get_db), _=Depends(require_roles("admin"))
) -> UpdatePeriod:
    period = UpdatePeriod(id=uuid.uuid4(), status=UpdatePeriodStatus.open, **payload.model_dump())
    db.add(period)
    db.commit()
    db.refresh(period)
    return period


@router.post("/{period_id}/close", response_model=UpdatePeriodOut)
def close_update_period(
    period_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(require_roles("admin"))
) -> UpdatePeriod:
    period = db.get(UpdatePeriod, period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Update period not found")
    period.status = UpdatePeriodStatus.closed
    period.closed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(period)
    return period


@router.post("/{period_id}/submit", response_model=UpdatePeriodOut)
def submit_scope(
    period_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("subcontractor")),
) -> UpdatePeriod:
    period = db.get(UpdatePeriod, period_id)
    if not period or period.status != UpdatePeriodStatus.open:
        raise HTTPException(status_code=400, detail="Update period is not open")
    if not user.company_id:
        raise HTTPException(status_code=400, detail="User has no assigned company")

    existing = (
        db.query(ScopeSubmission)
        .filter(
            ScopeSubmission.update_period_id == period_id,
            ScopeSubmission.company_id == user.company_id,
        )
        .first()
    )
    if not existing:
        db.add(
            ScopeSubmission(
                id=uuid.uuid4(),
                update_period_id=period_id,
                company_id=user.company_id,
                submitted_by_user_id=user.id,
            )
        )
        db.commit()
    return period


@router.post("/{period_id}/remind")
def remind_non_responders(
    period_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(require_roles("admin"))
) -> dict:
    period = db.get(UpdatePeriod, period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Update period not found")

    submitted_company_ids = {
        row.company_id
        for row in db.query(ScopeSubmission).filter(ScopeSubmission.update_period_id == period_id).all()
    }

    query = db.query(User).filter(User.role == UserRole.subcontractor, User.company_id.isnot(None))
    if submitted_company_ids:
        query = query.filter(~User.company_id.in_(submitted_company_ids))
    non_responders = query.all()

    for user in non_responders:
        send_reminder_email(
            user.email,
            f"Reminder: {period.label} closes soon",
            f"Please submit your scope updates for {period.label}.",
        )

    return {"reminded": len(non_responders)}
