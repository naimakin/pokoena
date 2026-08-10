import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user, require_roles
from app.models.activity import Activity
from app.models.activity_relationship import ActivityRelationship
from app.models.change_request import ChangeRequest, ChangeRequestStatus
from app.models.company import Company
from app.models.update_period import UpdatePeriod, UpdatePeriodStatus
from app.models.user import User, UserRole
from app.schemas.change_request import BulkApproveRequest, ChangeRequestCreate, ChangeRequestOut

router = APIRouter(prefix="/change-requests", tags=["change-requests"])


def _without_display_fields(change_request: ChangeRequest) -> ChangeRequest:
    """The create/approve/reject/bulk-approve endpoints return a bare row — set the
    list-only display fields to None explicitly rather than relying on ChangeRequestOut's
    field defaults to cover an attribute that was never set on this ORM instance."""
    change_request.requested_by_name = None
    change_request.requested_by_company = None
    change_request.activity_name = None
    change_request.activity_external_id = None
    return change_request


@router.post("", response_model=ChangeRequestOut, status_code=status.HTTP_201_CREATED)
def create_change_request(
    payload: ChangeRequestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("subcontractor")),
) -> ChangeRequest:
    period = db.get(UpdatePeriod, payload.update_period_id)
    if not period or period.status != UpdatePeriodStatus.open:
        raise HTTPException(status_code=400, detail="Update period is not open")

    if payload.activity_id:
        activity = db.get(Activity, payload.activity_id)
        if not activity or activity.company_id != user.company_id:
            raise HTTPException(status_code=403, detail="Not your scope")

    if payload.activity_relationship_id:
        relationship = db.get(ActivityRelationship, payload.activity_relationship_id)
        if not relationship:
            raise HTTPException(status_code=404, detail="Relationship not found")
        touched_activities = (
            db.query(Activity)
            .filter(Activity.id.in_([relationship.predecessor_id, relationship.successor_id]))
            .all()
        )
        if not any(a.company_id == user.company_id for a in touched_activities):
            raise HTTPException(status_code=403, detail="Not your scope")

    change_request = ChangeRequest(id=uuid.uuid4(), requested_by_user_id=user.id, **payload.model_dump())
    db.add(change_request)
    db.commit()
    db.refresh(change_request)
    return _without_display_fields(change_request)


@router.get("", response_model=list[ChangeRequestOut])
def list_change_requests(
    update_period_id: uuid.UUID,
    status_filter: ChangeRequestStatus | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ChangeRequest]:
    if user.role not in (UserRole.admin, UserRole.subcontractor):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted")

    query = db.query(ChangeRequest).filter(ChangeRequest.update_period_id == update_period_id)
    # Subcontractors only ever see their own flagged changes; admins see everyone's.
    if user.role == UserRole.subcontractor:
        query = query.filter(ChangeRequest.requested_by_user_id == user.id)
    if status_filter:
        query = query.filter(ChangeRequest.status == status_filter)
    items = query.order_by(ChangeRequest.created_at.desc()).all()

    requester_ids = {item.requested_by_user_id for item in items}
    activity_ids = {item.activity_id for item in items if item.activity_id}

    users_by_id = {u.id: u for u in db.query(User).filter(User.id.in_(requester_ids)).all()} if requester_ids else {}
    companies_by_id = {c.id: c for c in db.query(Company).all()}
    activities_by_id = (
        {a.id: a for a in db.query(Activity).filter(Activity.id.in_(activity_ids)).all()}
        if activity_ids
        else {}
    )

    # Transient attributes (never committed) so response_model's from_attributes
    # conversion can pick them up alongside the mapped columns.
    for item in items:
        requester = users_by_id.get(item.requested_by_user_id)
        item.requested_by_name = requester.full_name if requester else None
        item.requested_by_company = (
            companies_by_id[requester.company_id].name
            if requester and requester.company_id in companies_by_id
            else None
        )
        activity = activities_by_id.get(item.activity_id) if item.activity_id else None
        item.activity_name = activity.name if activity else None
        item.activity_external_id = activity.external_id if activity else None

    return items


def _resolve(db: Session, change_request: ChangeRequest, reviewer: User, new_status: ChangeRequestStatus) -> None:
    change_request.status = new_status
    change_request.reviewed_by_user_id = reviewer.id
    change_request.reviewed_at = datetime.now(timezone.utc)


@router.post("/{change_request_id}/approve", response_model=ChangeRequestOut)
def approve_change_request(
    change_request_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> ChangeRequest:
    change_request = db.get(ChangeRequest, change_request_id)
    if not change_request:
        raise HTTPException(status_code=404, detail="Change request not found")
    _resolve(db, change_request, user, ChangeRequestStatus.approved)
    db.commit()
    db.refresh(change_request)
    return _without_display_fields(change_request)


@router.post("/{change_request_id}/reject", response_model=ChangeRequestOut)
def reject_change_request(
    change_request_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> ChangeRequest:
    change_request = db.get(ChangeRequest, change_request_id)
    if not change_request:
        raise HTTPException(status_code=404, detail="Change request not found")
    _resolve(db, change_request, user, ChangeRequestStatus.rejected)
    db.commit()
    db.refresh(change_request)
    return _without_display_fields(change_request)


@router.post("/bulk-approve", response_model=list[ChangeRequestOut])
def bulk_approve(
    payload: BulkApproveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> list[ChangeRequest]:
    items = db.query(ChangeRequest).filter(ChangeRequest.id.in_(payload.ids)).all()
    for change_request in items:
        _resolve(db, change_request, user, ChangeRequestStatus.approved)
    db.commit()
    for change_request in items:
        db.refresh(change_request)
    return [_without_display_fields(item) for item in items]
