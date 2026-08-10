import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user
from app.models.activity import Activity, ActivityStatus
from app.models.activity_relationship import ActivityRelationship
from app.models.update_period import UpdatePeriod, UpdatePeriodStatus
from app.models.user import User, UserRole
from app.schemas.activity import ActivityOut, ActivityRelationshipOut, ActivityUpdate

router = APIRouter(prefix="/activities", tags=["activities"])


@router.get("", response_model=list[ActivityOut])
def list_activities(
    project_id: uuid.UUID,
    mine: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Activity]:
    query = db.query(Activity).filter(Activity.project_id == project_id)
    if mine or user.role == UserRole.subcontractor:
        if not user.company_id:
            return []
        query = query.filter(Activity.company_id == user.company_id)
    return query.order_by(Activity.external_id).all()


@router.get("/{activity_id}/relationships", response_model=list[ActivityRelationshipOut])
def list_activity_relationships(
    activity_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(get_current_user)
) -> list[ActivityRelationship]:
    relationships = (
        db.query(ActivityRelationship)
        .filter(
            (ActivityRelationship.predecessor_id == activity_id)
            | (ActivityRelationship.successor_id == activity_id)
        )
        .all()
    )

    other_ids = {
        other_id
        for rel in relationships
        for other_id in (rel.predecessor_id, rel.successor_id)
        if other_id != activity_id
    }
    activities_by_id = (
        {a.id: a for a in db.query(Activity).filter(Activity.id.in_(other_ids)).all()} if other_ids else {}
    )

    for rel in relationships:
        predecessor = activities_by_id.get(rel.predecessor_id)
        successor = activities_by_id.get(rel.successor_id)
        rel.predecessor_external_id = predecessor.external_id if predecessor else None
        rel.successor_external_id = successor.external_id if successor else None

    return relationships


@router.patch("/{activity_id}", response_model=ActivityOut)
def update_activity(
    activity_id: uuid.UUID,
    payload: ActivityUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Activity:
    activity = db.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    if user.role == UserRole.subcontractor:
        if activity.company_id != user.company_id:
            raise HTTPException(status_code=403, detail="Not your scope")
        open_period = (
            db.query(UpdatePeriod)
            .filter(
                UpdatePeriod.project_id == activity.project_id,
                UpdatePeriod.status == UpdatePeriodStatus.open,
            )
            .first()
        )
        if not open_period:
            raise HTTPException(status_code=400, detail="No open update period for this project")
    elif user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Not permitted")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(activity, field, value)

    if "percent_complete" in changes:
        if activity.percent_complete >= 100:
            activity.status = ActivityStatus.complete
        elif activity.percent_complete > 0:
            activity.status = ActivityStatus.in_progress
        else:
            activity.status = ActivityStatus.not_started

    db.commit()
    db.refresh(activity)
    return activity
