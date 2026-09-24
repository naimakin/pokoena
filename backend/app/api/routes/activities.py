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
from app.models.activity_event import ActivityEvent
from app.models.activity_relationship import ActivityRelationship
from app.models.project import Project
from app.models.schedule_import import ScheduleImport
from app.models.update_period import UpdatePeriod, UpdatePeriodStatus
from app.models.user import User
from app.models.user_tenant_role import TenantRole
from app.schemas.activity import (
    ActivityBatchResultOut,
    ActivityBatchRowError,
    ActivityBatchUpdateIn,
    ActivityCommentIn,
    ActivityHistoryItemOut,
    ActivityOut,
    ActivityRelationshipOut,
    ActivityUpdate,
)

router = APIRouter(prefix="/activities", tags=["activities"])

# actual_start / actual_finish are nullable (a null clears them); percent_complete
# and remaining_duration_days are NOT NULL, so an explicit null there means
# "field omitted" and must be skipped rather than written.
_NULLABLE_EDIT_FIELDS = {"actual_start", "actual_finish", "notes"}

# What the Activity modal's History tab reports on a user edit. `status` is in
# here even though it isn't directly settable: it's derived from the actual
# dates (see _apply_progress_derivation), and "To Do -> In Progress" is the
# change a reader actually cares about.
_TRACKED_EDIT_FIELDS = (
    "status",
    "percent_complete",
    "actual_start",
    "actual_finish",
    "remaining_duration_days",
    "is_important",
    "tags",
    "notes",
)

# Fields whose movement between two consecutive imports is worth showing in the
# same timeline. Keys are as written into ScheduleImport.activities_snapshot.
_TRACKED_VERSION_FIELDS = (
    "planned_start",
    "planned_finish",
    "early_start",
    "early_finish",
    "total_float_hours",
    "is_critical",
)

# How far back the version diff walks. A project accumulates an import per
# update cycle, and the snapshots are full-programme JSON blobs, so reading all
# of them to render one activity's timeline gets expensive on a long-running
# project; the recent ones are what anyone actually reads.
_VERSION_HISTORY_IMPORTS = 8


def _event_value(value) -> str | None:
    """Render a field value for the timeline. Strings, so old/new stay
    comparable and printable whatever the column type was."""
    if value is None:
        return None
    if isinstance(value, ActivityStatus):
        return value.value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) or None
    return str(value)[:255]


def _edit_snapshot(activity: Activity) -> dict[str, str | None]:
    return {field: _event_value(getattr(activity, field)) for field in _TRACKED_EDIT_FIELDS}


def _record_edit_events(
    db: Session, ctx: AuthContext, activity: Activity, before: dict[str, str | None]
) -> None:
    """One activity_events row per changed field, added to the caller's session
    so it commits atomically with the change itself."""
    after = _edit_snapshot(activity)
    for field in _TRACKED_EDIT_FIELDS:
        if before[field] == after[field]:
            continue
        db.add(
            ActivityEvent(
                id=uuid.uuid4(),
                tenant_id=ctx.tenant_id,
                project_id=activity.project_id,
                activity_id=activity.id,
                actor_user_id=ctx.user.id,
                kind="change",
                field=field,
                old_value=before[field],
                new_value=after[field],
            )
        )


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
            before = _edit_snapshot(activity)
            _apply_changes(activity, changes)
            _apply_progress_derivation(activity, changes)
            _record_edit_events(db, ctx, activity, before)
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
    before = _edit_snapshot(activity)
    _apply_changes(activity, changes)
    _apply_progress_derivation(activity, changes)
    _record_edit_events(db, ctx, activity, before)

    db.commit()
    db.refresh(activity)
    return activity


@router.post("/{activity_id}/comments", response_model=ActivityHistoryItemOut, status_code=201)
def add_activity_comment(
    activity_id: uuid.UUID,
    payload: ActivityCommentIn,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> ActivityHistoryItemOut:
    """A comment on an activity, landing in the same timeline as field changes.
    Unlike an edit this needs no open update period — being unable to say "this
    is blocked on the permit" until a period opens would defeat the point."""
    activity = get_tenant_scoped_or_404(db, Activity, activity_id, ctx)
    require_project_permission(db, activity.project_id, ctx)
    require_scope_access(activity.project_scope_id, ctx)

    event = ActivityEvent(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        project_id=activity.project_id,
        activity_id=activity.id,
        actor_user_id=ctx.user.id,
        kind="comment",
        body=payload.body.strip(),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return ActivityHistoryItemOut(
        kind="comment",
        created_at=event.created_at,
        actor_name=ctx.user.full_name,
        body=event.body,
    )


@router.get("/{activity_id}/history", response_model=list[ActivityHistoryItemOut])
def activity_history(
    activity_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> list[ActivityHistoryItemOut]:
    """The Activity modal's History tab: user edits and comments (stored in
    activity_events) merged with programme-driven date/float movement, newest
    first.

    The programme side is derived on read by diffing this activity's entry in
    consecutive `ScheduleImport.activities_snapshot` blobs rather than stored:
    the import path stays untouched, and the history works retroactively for
    programmes uploaded before any of this existed."""
    activity = get_tenant_scoped_or_404(db, Activity, activity_id, ctx)
    require_project_permission(db, activity.project_id, ctx)
    require_scope_access(activity.project_scope_id, ctx)

    items: list[ActivityHistoryItemOut] = []

    events = (
        db.query(ActivityEvent)
        .filter(ActivityEvent.tenant_id == ctx.tenant_id, ActivityEvent.activity_id == activity_id)
        .order_by(ActivityEvent.created_at.desc())
        .limit(200)
        .all()
    )
    actor_ids = {e.actor_user_id for e in events if e.actor_user_id}
    actors = (
        {u.id: u.full_name for u in db.query(User).filter(User.id.in_(actor_ids)).all()}
        if actor_ids
        else {}
    )
    for event in events:
        items.append(
            ActivityHistoryItemOut(
                kind=event.kind,
                created_at=event.created_at,
                actor_name=actors.get(event.actor_user_id) if event.actor_user_id else None,
                field=event.field,
                old_value=event.old_value,
                new_value=event.new_value,
                body=event.body,
            )
        )

    imports = (
        db.query(ScheduleImport)
        .filter(
            ScheduleImport.tenant_id == ctx.tenant_id,
            ScheduleImport.project_id == activity.project_id,
        )
        .order_by(ScheduleImport.imported_at.desc())
        .limit(_VERSION_HISTORY_IMPORTS)
        .all()
    )
    # Back to chronological order so each import is compared with the one before it.
    imports.reverse()
    previous: dict | None = None
    for schedule_import in imports:
        entry = next(
            (
                row
                for row in (schedule_import.activities_snapshot or [])
                if row.get("external_id") == activity.external_id
            ),
            None,
        )
        if entry is None:
            continue
        if previous is not None:
            for field in _TRACKED_VERSION_FIELDS:
                old_value = _event_value(previous.get(field))
                new_value = _event_value(entry.get(field))
                if old_value == new_value:
                    continue
                items.append(
                    ActivityHistoryItemOut(
                        kind="version",
                        created_at=schedule_import.imported_at,
                        field=field,
                        old_value=old_value,
                        new_value=new_value,
                        revision_label=schedule_import.revision_label or schedule_import.filename,
                    )
                )
        previous = entry

    items.sort(key=lambda i: i.created_at, reverse=True)
    return items
