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
from app.schemas.activity import (
    ActivityBatchResultOut,
    ActivityBatchRowError,
    ActivityBatchUpdateIn,
    ActivityOut,
    ActivityRelationshipOut,
    ActivityUpdate,
)

router = APIRouter(prefix="/activities", tags=["activities"])

# actual_start / actual_finish are nullable (a null clears them); percent_complete
# and remaining_duration_days are NOT NULL, so an explicit null there means
# "field omitted" and must be skipped rather than written.
_NULLABLE_EDIT_FIELDS = {"actual_start", "actual_finish"}


def _apply_changes(activity: Activity, changes: dict) -> None:
    for field, value in changes.items():
        if value is None and field not in _NULLABLE_EDIT_FIELDS:
            continue
        setattr(activity, field, value)


def _authorize_progress_edit(db: Session, project_id: uuid.UUID, ctx: AuthContext) -> None:
    """Project-level gate shared by the single PATCH and the batch endpoint.
    Subcontractors additionally need per-row scope access, checked by the caller."""
    if ctx.role == TenantRole.subcontractor:
        if not ctx.scope_ids:
            raise HTTPException(status_code=403, detail="Not permitted")
        open_period = (
            db.query(UpdatePeriod)
            .filter(
                UpdatePeriod.project_id == project_id,
                UpdatePeriod.status == UpdatePeriodStatus.open,
            )
            .first()
        )
        if not open_period:
            raise HTTPException(status_code=400, detail="No open update period for this project")
    elif ctx.role == TenantRole.company_employee:
        require_project_permission(db, project_id, ctx, need_edit=True)
    elif ctx.role != TenantRole.company_admin:
        raise HTTPException(status_code=403, detail="Not permitted")


def _apply_progress_derivation(activity: Activity, changes: dict) -> None:
    """Keep status / % / remaining consistent after an edit. Precedence follows
    P6: actual_finish > actual_start > percent_complete. Raises HTTPException(422)
    on an inconsistent actual-date pair — callers turn that into a per-row error
    (batch) or a 422 response (single)."""
    touched_dates = {"actual_start", "actual_finish"} & changes.keys()
    if not touched_dates:
        # A percent_complete-only edit uses the legacy 3-way rule, but only
        # while the activity isn't already actual-date-driven.
        if "percent_complete" in changes and activity.actual_start is None and activity.actual_finish is None:
            pc = activity.percent_complete or 0
            activity.status = (
                ActivityStatus.complete
                if pc >= 100
                else ActivityStatus.in_progress
                if pc > 0
                else ActivityStatus.not_started
            )
        return

    if activity.actual_finish is not None:
        if activity.actual_start is None:
            raise HTTPException(status_code=422, detail="Actual Finish requires an Actual Start")
        if activity.actual_start > activity.actual_finish:
            raise HTTPException(status_code=422, detail="Actual Finish is before Actual Start")
        activity.status = ActivityStatus.complete
        activity.percent_complete = 100
        activity.remaining_duration_days = 0
    elif activity.actual_start is not None:
        activity.status = ActivityStatus.in_progress
        if activity.percent_complete >= 100:
            activity.percent_complete = 99
    else:  # both actual dates cleared
        activity.status = ActivityStatus.not_started
        activity.percent_complete = 0
        if activity.target_duration_hours:
            activity.remaining_duration_days = round(activity.target_duration_hours / 8.0)


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


@router.patch("", response_model=ActivityBatchResultOut)
def batch_update_activities(
    project_id: uuid.UUID,
    payload: ActivityBatchUpdateIn,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> ActivityBatchResultOut:
    """Company-side "Save all" from the Progress page. One request, one auth
    pass, one commit; each row succeeds or fails independently (client-side
    validation keeps failures rare). Subcontractor edits still use the single
    PATCH below (one field at a time, from the scope card)."""
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    _authorize_progress_edit(db, project_id, ctx)

    ids = [item.id for item in payload.updates]
    rows = {
        a.id: a
        for a in db.query(Activity).filter(
            Activity.tenant_id == ctx.tenant_id,
            Activity.project_id == project_id,
            Activity.id.in_(ids),
        )
    }

    saved: list[Activity] = []
    failed: list[ActivityBatchRowError] = []
    for item in payload.updates:
        activity = rows.get(item.id)
        if activity is None:
            failed.append(ActivityBatchRowError(id=item.id, error="Activity not found in this project"))
            continue
        try:
            if ctx.role == TenantRole.subcontractor:
                require_scope_access(activity.project_scope_id, ctx)
            changes = item.model_dump(exclude_unset=True, exclude={"id"})
            _apply_changes(activity, changes)
            _apply_progress_derivation(activity, changes)
            saved.append(activity)
        except HTTPException as exc:
            db.expire(activity)  # discard the in-memory mutation (nothing flushed yet)
            failed.append(ActivityBatchRowError(id=item.id, error=str(exc.detail)))

    db.commit()
    for activity in saved:
        db.refresh(activity)
    return ActivityBatchResultOut(saved=saved, failed=failed)


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
    _authorize_progress_edit(db, activity.project_id, ctx)

    changes = payload.model_dump(exclude_unset=True)
    _apply_changes(activity, changes)
    _apply_progress_derivation(activity, changes)

    db.commit()
    db.refresh(activity)
    return activity
