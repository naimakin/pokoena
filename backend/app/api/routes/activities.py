import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import (
    AuthContext,
    get_current_tenant_user,
    get_tenant_scoped_or_404,
    require_project_permission,
    require_scope_access,
)
from app.models.activity import Activity, ActivityStatus
from app.models.activity_relationship import ActivityRelationship
from app.models.project import Project
from app.models.update_period import UpdatePeriod, UpdatePeriodStatus
from app.models.user_tenant_role import TenantRole
from app.schemas.activity import ActivityOut, ActivityRelationshipOut, ActivityUpdate

router = APIRouter(prefix="/activities", tags=["activities"])


@router.get("", response_model=list[ActivityOut])
def list_activities(
    project_id: uuid.UUID,
    mine: bool = False,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> list[Activity]:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)

    query = db.query(Activity).filter(Activity.tenant_id == ctx.tenant_id, Activity.project_id == project_id)
    if mine or ctx.role == TenantRole.subcontractor:
        if not ctx.scope_ids:
            return []
        query = query.filter(Activity.project_scope_id.in_(ctx.scope_ids))
    return query.order_by(Activity.external_id).all()


@router.get("/{activity_id}/relationships", response_model=list[ActivityRelationshipOut])
def list_activity_relationships(
    activity_id: uuid.UUID, db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)
) -> list[ActivityRelationship]:
    activity = get_tenant_scoped_or_404(db, Activity, activity_id, ctx)
    require_project_permission(db, activity.project_id, ctx)
    require_scope_access(activity.project_scope_id, ctx)

    relationships = (
        db.query(ActivityRelationship)
        .filter(
            ActivityRelationship.tenant_id == ctx.tenant_id,
            (ActivityRelationship.predecessor_id == activity_id)
            | (ActivityRelationship.successor_id == activity_id),
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
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> Activity:
    activity = get_tenant_scoped_or_404(db, Activity, activity_id, ctx)

    if ctx.role == TenantRole.subcontractor:
        require_scope_access(activity.project_scope_id, ctx)
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
    elif ctx.role == TenantRole.company_employee:
        require_project_permission(db, activity.project_id, ctx, need_edit=True)
    elif ctx.role != TenantRole.company_admin:
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
