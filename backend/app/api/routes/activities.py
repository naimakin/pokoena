import uuid
from dataclasses import dataclass
from datetime import date

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
from app.engine.durations import activity_hours_per_day
from app.models.activity import FINISH_MILESTONE, MILESTONE_TYPES, P6_STATUS_CODE, Activity, ActivityStatus
from app.models.activity_event import ActivityEvent
from app.models.activity_relationship import ActivityRelationship
from app.models.project import Project
from app.models.resource import LABOR, Resource
from app.models.resource_assignment import ResourceAssignment
from app.models.schedule_import import ScheduleImport
from app.models.update_period import UpdatePeriod, UpdatePeriodStatus
from app.models.user import User
from app.models.user_tenant_role import TenantRole
from app.schemas.activity import (
    ActivityAssignmentOut,
    ActivityBatchResultOut,
    ActivityBatchRowError,
    ActivityBatchUpdateIn,
    ActivityCommentIn,
    ActivityHistoryItemOut,
    ActivityOut,
    ActivityRelationshipOut,
    ActivityUpdate,
)
from app.services.activity_progress import apply_progress_entry, clear_float_if_finished
from app.services.criticality import annotate_criticality
from app.services.schedule_current import get_current_import

router = APIRouter(prefix="/activities", tags=["activities"])

# actual_start / actual_finish are nullable (a null clears them); percent_complete
# and remaining_duration_days are NOT NULL, so an explicit null there means
# "field omitted" and must be skipped rather than written.
_NULLABLE_EDIT_FIELDS = {"actual_start", "actual_finish", "notes", "site_risk"}

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
    "site_risk",
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


def _effective_changes(activity: Activity, changes: dict) -> dict:
    """The submitted fields that actually change something. The Activity modal
    sends every field on each save, and "the user typed a %" has to mean the %
    moved — not that it rode along with an actual-date edit — because a % entry
    rewrites units / remaining duration (services/activity_progress.py)."""
    return {
        field: value
        for field, value in changes.items()
        if (value is not None or field in _NULLABLE_EDIT_FIELDS) and getattr(activity, field) != value
    }


def _apply_changes(activity: Activity, changes: dict) -> None:
    for field, value in changes.items():
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


def _apply_progress_derivation(activity: Activity, changes: dict, data_date: date) -> None:
    """Keep status / % / remaining consistent after an edit, then mirror the
    status into P6's TASK.status_code. Precedence follows P6: actual_finish >
    actual_start > percent_complete. Raises HTTPException(422) on an
    inconsistent actual-date pair — callers turn that into a per-row error
    (batch) or a 422 response (single). `data_date` is the programme's data
    date, the actual date a %-only entry stands on (see below)."""
    _derive_status(activity, changes, data_date)
    if _PROGRESS_FIELDS & changes.keys():
        activity.status_code = P6_STATUS_CODE[activity.status]


def _derive_status(activity: Activity, changes: dict, data_date: date) -> None:
    if activity.task_type in MILESTONE_TYPES:
        if _PROGRESS_FIELDS & changes.keys():
            _derive_milestone_status(activity, changes)
        return
    touched_dates = {"actual_start", "actual_finish"} & changes.keys()
    if not touched_dates:
        # A percent_complete-only edit uses the legacy 3-way rule, but only
        # while the activity isn't already actual-date-driven. An activity P6
        # calls started has an actual start (TK_Active without act_start_date
        # isn't a state P6 writes), so a % on one that hasn't started starts it
        # on the data date — what P6 itself fills in when "Started" is ticked —
        # and 100% finishes it there too.
        if "percent_complete" in changes and activity.actual_start is None and activity.actual_finish is None:
            pc = activity.percent_complete or 0
            if pc >= 100:
                activity.status = ActivityStatus.complete
                activity.actual_start = activity.actual_finish = data_date
            elif pc > 0:
                activity.status = ActivityStatus.in_progress
                activity.actual_start = data_date
            else:
                activity.status = ActivityStatus.not_started
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
        _reset_to_not_started(activity)


def _derive_milestone_status(activity: Activity, changes: dict) -> None:
    """A milestone has one moment — Start for TT_Mile, Finish for TT_FinMile —
    so recording either actual date completes it; there is no in-progress
    milestone. P6 stores that moment in BOTH act_start_date and act_end_date,
    so both are set to it. The milestone's own date (the one the Activity
    modal shows) governs: entered, it completes the milestone; cleared, it
    puts the milestone back to Not Started, other date and all."""
    own, other = (
        ("actual_finish", "actual_start") if activity.task_type == FINISH_MILESTONE else ("actual_start", "actual_finish")
    )
    if own in changes:
        moment = getattr(activity, own)
    elif other in changes:
        moment = getattr(activity, other)
    else:
        moment = getattr(activity, own) or getattr(activity, other)
    if moment is None:
        activity.actual_start = activity.actual_finish = None
        _reset_to_not_started(activity)
        return
    activity.actual_start = activity.actual_finish = moment
    activity.status = ActivityStatus.complete
    activity.percent_complete = 100
    activity.remaining_duration_days = 0


def _data_date(db: Session, ctx: AuthContext, project_id: uuid.UUID) -> date:
    """The current programme's data date; today for a project without one."""
    current = get_current_import(db, ctx.tenant_id, project_id)
    return current.data_date.date() if current is not None and current.data_date else date.today()


def _reset_to_not_started(activity: Activity) -> None:
    activity.status = ActivityStatus.not_started
    activity.percent_complete = 0
    if activity.target_duration_hours:
        activity.remaining_duration_days = round(activity.target_duration_hours / activity_hours_per_day(activity))


_PROGRESS_FIELDS = {"percent_complete", "actual_start", "actual_finish"}
# Edits that move % / units / remaining duration (services/activity_progress.py).
_SIDE_EFFECT_FIELDS = _PROGRESS_FIELDS | {"remaining_duration_days"}


@dataclass
class _ProgressEdit:
    activity: Activity
    changed: set[str]
    status_before: ActivityStatus


def _apply_progress_side_effects(db: Session, edits: list[_ProgressEdit]) -> None:
    """Float, resource units, physical % and remaining duration follow a
    progress edit, and the displayed % is re-derived — see
    services/activity_progress.py. One query for the whole batch."""
    if not edits:
        return
    labor_by_activity: dict[uuid.UUID, list[ResourceAssignment]] = {}
    nonlabor_by_activity: dict[uuid.UUID, list[ResourceAssignment]] = {}
    for assignment, rsrc_type in (
        db.query(ResourceAssignment, Resource.rsrc_type)
        .join(Resource, Resource.id == ResourceAssignment.resource_id)
        .filter(ResourceAssignment.activity_id.in_([e.activity.id for e in edits]))
    ):
        bucket = labor_by_activity if rsrc_type == LABOR else nonlabor_by_activity
        bucket.setdefault(assignment.activity_id, []).append(assignment)
    for edit in edits:
        activity = edit.activity
        clear_float_if_finished(activity)
        apply_progress_entry(
            activity,
            labor_by_activity.get(activity.id, []),
            nonlabor=nonlabor_by_activity.get(activity.id, []),
            pct_entered="percent_complete" in edit.changed,
            remaining_entered="remaining_duration_days" in edit.changed,
            status_changed=activity.status != edit.status_before,
        )


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
    # An .xer is a full snapshot: importing one prunes WBS nodes that are no
    # longer in the file, but activity rows are deliberately kept, because they
    # carry subcontractor progress, comments and annotations (see services/
    # xer_import.py). An activity dropped from the programme therefore survived
    # with a wbs_path pointing at a node that no longer exists, so every grid
    # showed it under "Ungrouped" as if it were live work, and it kept inflating
    # the project's activity counts. It isn't part of the current programme, so
    # it doesn't belong in this list — Execution > Changes is where a removed
    # activity is reported, off the frozen per-import snapshots. The row itself
    # is never deleted, and returns here as soon as an import brings it back.
    #
    # last_import_id IS NULL means the activity was created by a user, or its
    # import was deleted (routes/schedule_imports.py nulls the column rather
    # than orphaning the row), so those always stay listed.
    current_import = get_current_import(db, ctx.tenant_id, project_id)
    if current_import is not None:
        query = query.filter(
            (Activity.last_import_id.is_(None)) | (Activity.last_import_id == current_import.id)
        )
    activities = query.order_by(Activity.external_id).all()
    annotate_criticality(db, ctx.tenant_id, project_id, activities)
    return activities


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


@router.get("/{activity_id}/assignments", response_model=list[ActivityAssignmentOut])
def list_activity_assignments(
    activity_id: uuid.UUID, db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)
) -> list[ActivityAssignmentOut]:
    """The activity's resource assignments (P6 TASKRSRC) with their units —
    the Activity modal's Details tab."""
    activity = get_tenant_scoped_or_404(db, Activity, activity_id, ctx)
    require_project_permission(db, activity.project_id, ctx)
    require_scope_access(activity.project_scope_id, ctx)

    rows = (
        db.query(ResourceAssignment, Resource)
        .join(Resource, Resource.id == ResourceAssignment.resource_id)
        .filter(ResourceAssignment.tenant_id == ctx.tenant_id, ResourceAssignment.activity_id == activity_id)
        .all()
    )
    out = [
        ActivityAssignmentOut(
            id=a.id,
            rsrc_id=r.rsrc_id,
            name=r.name,
            short_name=r.short_name,
            rsrc_type=r.rsrc_type,
            unit_id=a.unit_id or r.unit_id,
            target_qty=a.target_qty or 0.0,
            act_reg_qty=a.act_reg_qty or 0.0,
            remain_qty=a.remain_qty or 0.0,
        )
        for a, r in rows
    ]
    # Labor first (it drives the %), then by name.
    out.sort(key=lambda o: (o.rsrc_type != LABOR, o.name))
    return out


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

    data_date = _data_date(db, ctx, project_id)
    saved: list[Activity] = []
    progressed: list[_ProgressEdit] = []
    before_by_id: dict[uuid.UUID, dict[str, str | None]] = {}
    failed: list[ActivityBatchRowError] = []
    for item in payload.updates:
        activity = rows.get(item.id)
        if activity is None:
            failed.append(ActivityBatchRowError(id=item.id, error="Activity not found in this project"))
            continue
        try:
            if ctx.role == TenantRole.subcontractor:
                require_scope_access(activity.project_scope_id, ctx)
            changes = _effective_changes(activity, item.model_dump(exclude_unset=True, exclude={"id"}))
            before_by_id[activity.id] = _edit_snapshot(activity)
            status_before = activity.status
            _apply_changes(activity, changes)
            _apply_progress_derivation(activity, changes, data_date)
            saved.append(activity)
            if _SIDE_EFFECT_FIELDS & changes.keys():
                progressed.append(_ProgressEdit(activity, set(changes), status_before))
        except HTTPException as exc:
            db.expire(activity)  # discard the in-memory mutation (nothing flushed yet)
            failed.append(ActivityBatchRowError(id=item.id, error=str(exc.detail)))

    # Events after the side effects, so the History tab records the % that was
    # actually stored (it is re-derived — services/activity_progress.py).
    _apply_progress_side_effects(db, progressed)
    for activity in saved:
        _record_edit_events(db, ctx, activity, before_by_id[activity.id])
    db.commit()
    for activity in saved:
        db.refresh(activity)
    annotate_criticality(db, ctx.tenant_id, project_id, saved)
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

    changes = _effective_changes(activity, payload.model_dump(exclude_unset=True))
    before = _edit_snapshot(activity)
    status_before = activity.status
    _apply_changes(activity, changes)
    _apply_progress_derivation(activity, changes, _data_date(db, ctx, activity.project_id))
    if _SIDE_EFFECT_FIELDS & changes.keys():
        _apply_progress_side_effects(db, [_ProgressEdit(activity, set(changes), status_before)])
    _record_edit_events(db, ctx, activity, before)

    db.commit()
    db.refresh(activity)
    annotate_criticality(db, ctx.tenant_id, activity.project_id, [activity])
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
