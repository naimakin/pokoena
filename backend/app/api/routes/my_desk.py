import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import (
    AuthContext,
    get_current_tenant_user,
    get_tenant_scoped_or_404,
    require_capability,
    require_project_permission,
)
from app.models.activity import Activity
from app.models.activity_event import ActivityEvent
from app.models.mention import Mention, MentionKind
from app.models.my_desk import ActivityPin, PersonalNote
from app.models.user import User
from app.models.project import Project
from app.models.recovery_plan import RecoveryPlan, RecoveryPlanItem
from app.models.user_tenant_role import Capability, TenantRole
from app.schemas.my_desk import (
    ActivityDeskOut,
    InboxItemOut,
    MentionCountOut,
    MentionOut,
    NoteCreate,
    NoteOut,
    NoteUpdate,
    PinOut,
    SuggestionOut,
)
from app.services.my_desk import (
    build_inbox,
    build_pins,
    build_suggestions,
    note_out,
    pin_snapshot,
    sort_notes,
)
from app.services.portfolio import visible_projects

router = APIRouter(prefix="/my-desk", tags=["my-desk"])

# The company shell's page; subcontractors have their own scope pages.
_ROLE = require_capability(Capability.view_delivery)


def _projects(db: Session, ctx: AuthContext, project_id: uuid.UUID | None) -> list[Project]:
    """One project (checked) or every project the caller can see — so a desk
    never shows a pin or note from a project the caller has since lost."""
    if project_id is not None:
        project = get_tenant_scoped_or_404(db, Project, project_id, ctx)
        require_project_permission(db, project_id, ctx)
        return [project]
    return visible_projects(db, ctx.tenant_id, ctx.user.id, ctx.role)


def _activity(db: Session, ctx: AuthContext, activity_id: uuid.UUID) -> Activity:
    activity = get_tenant_scoped_or_404(db, Activity, activity_id, ctx)
    require_project_permission(db, activity.project_id, ctx)
    return activity


def _own_note(db: Session, ctx: AuthContext, note_id: uuid.UUID) -> PersonalNote:
    note = get_tenant_scoped_or_404(db, PersonalNote, note_id, ctx)
    # Someone else's private note doesn't exist as far as the caller can tell.
    if note.user_id != ctx.user.id:
        raise HTTPException(status_code=404, detail="PersonalNote not found")
    return note


def _project_map(db: Session, ctx: AuthContext) -> dict[uuid.UUID, Project]:
    return {p.id: p for p in visible_projects(db, ctx.tenant_id, ctx.user.id, ctx.role)}


# ---------------------------------------------------------------- mentions
# Open to every signed-in tenant user, subcontractors included: being tagged is
# about you, not about a page. Every query filters on mentioned_user_id.


def _mentions_query(db: Session, ctx: AuthContext):
    return db.query(Mention).filter(Mention.tenant_id == ctx.tenant_id, Mention.mentioned_user_id == ctx.user.id)


@router.get("/mentions", response_model=list[MentionOut])
def list_mentions(
    unread: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> list[MentionOut]:
    query = _mentions_query(db, ctx)
    if unread:
        query = query.filter(Mention.read_at.is_(None))
    rows = query.order_by(Mention.created_at.desc()).limit(limit).all()
    event_ids = [m.activity_event_id for m in rows if m.activity_event_id]
    events = {
        e.id: e
        for e in db.query(ActivityEvent).filter(
            ActivityEvent.tenant_id == ctx.tenant_id, ActivityEvent.id.in_(event_ids)
        )
    } if event_ids else {}
    plan_ids = {m.recovery_plan_id for m in rows if m.recovery_plan_id}
    plans = {
        p.id: p
        for p in db.query(RecoveryPlan).filter(RecoveryPlan.tenant_id == ctx.tenant_id, RecoveryPlan.id.in_(plan_ids))
    } if plan_ids else {}
    item_ids = {m.recovery_item_id for m in rows if m.recovery_item_id}
    actions = dict(
        db.query(RecoveryPlanItem.id, RecoveryPlanItem.action).filter(
            RecoveryPlanItem.tenant_id == ctx.tenant_id, RecoveryPlanItem.id.in_(item_ids)
        )
    ) if item_ids else {}

    def body(m: Mention) -> str:
        if m.activity_event_id is not None:
            event = events.get(m.activity_event_id)
            return (event.body or "") if event is not None else ""
        if m.recovery_item_id is not None:
            return actions.get(m.recovery_item_id, "")
        plan = plans.get(m.recovery_plan_id)
        return (plan.summary or "") if plan is not None else ""

    def href(m: Mention) -> str | None:
        """A recovery-plan mention opens its row on the Recovery Plan page, on
        the comparison the plan was raised against."""
        if m.recovery_plan_id is None:
            return None
        params = {"activity": m.activity_external_id}
        plan = plans.get(m.recovery_plan_id)
        if ctx.role == TenantRole.subcontractor:
            return f"/scope/recovery-plan?{urlencode(params)}"
        if plan is not None and plan.from_import_id and plan.to_import_id:
            params = {"from": str(plan.from_import_id), "to": str(plan.to_import_id), **params}
        return f"/recovery-plan?{urlencode(params)}"

    names = dict(
        db.query(User.id, User.full_name).filter(User.id.in_({m.author_user_id for m in rows if m.author_user_id}))
    ) if rows else {}
    activities = dict(
        db.query(Activity.id, Activity.name).filter(Activity.id.in_({m.activity_id for m in rows if m.activity_id}))
    ) if rows else {}
    projects = {
        p.id: p for p in db.query(Project).filter(Project.id.in_({m.project_id for m in rows}))
    } if rows else {}
    return [
        MentionOut(
            id=m.id,
            project_id=m.project_id,
            project_code=projects[m.project_id].code if m.project_id in projects else "",
            activity_id=m.activity_id,
            activity_external_id=m.activity_external_id,
            activity_name=activities.get(m.activity_id),
            author_name=names.get(m.author_user_id),
            body=body(m),
            kind=m.kind or MentionKind.comment,
            event_id=m.activity_event_id,
            recovery_plan_id=m.recovery_plan_id,
            href=href(m),
            created_at=m.created_at,
            read_at=m.read_at,
        )
        for m in rows
    ]


@router.get("/mentions/count", response_model=MentionCountOut)
def count_mentions(db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)) -> MentionCountOut:
    return MentionCountOut(unread=_mentions_query(db, ctx).filter(Mention.read_at.is_(None)).count())


@router.post("/mentions/read-all", response_model=MentionCountOut)
def read_all_mentions(db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)) -> MentionCountOut:
    _mentions_query(db, ctx).filter(Mention.read_at.is_(None)).update(
        {Mention.read_at: datetime.now(timezone.utc)}, synchronize_session=False
    )
    db.commit()
    return MentionCountOut(unread=0)


@router.post("/mentions/{mention_id}/read", response_model=MentionCountOut)
def read_mention(
    mention_id: uuid.UUID, db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)
) -> MentionCountOut:
    mention = _mentions_query(db, ctx).filter(Mention.id == mention_id).first()
    if mention is None:
        # Someone else's mention doesn't exist as far as the caller can tell.
        raise HTTPException(status_code=404, detail="Mention not found")
    if mention.read_at is None:
        mention.read_at = datetime.now(timezone.utc)
        db.commit()
    return MentionCountOut(unread=_mentions_query(db, ctx).filter(Mention.read_at.is_(None)).count())


# ---------------------------------------------------------------- inbox / suggestions


@router.get("/inbox", response_model=list[InboxItemOut])
def get_inbox(
    project_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(_ROLE),
) -> list[InboxItemOut]:
    return build_inbox(db, ctx, _projects(db, ctx, project_id))


@router.get("/suggestions", response_model=list[SuggestionOut])
def get_suggestions(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(_ROLE),
) -> list[SuggestionOut]:
    return build_suggestions(db, ctx, _projects(db, ctx, project_id)[0])


# ---------------------------------------------------------------- pins


@router.get("/pins", response_model=list[PinOut])
def list_pins(
    project_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(_ROLE),
) -> list[PinOut]:
    projects = {p.id: p for p in _projects(db, ctx, project_id)}
    pins = (
        db.query(ActivityPin)
        .filter(
            ActivityPin.tenant_id == ctx.tenant_id,
            ActivityPin.user_id == ctx.user.id,
            ActivityPin.project_id.in_(list(projects)),
        )
        .all()
    )
    return build_pins(db, ctx, pins, projects)


def _pin_for(db: Session, ctx: AuthContext, activity: Activity) -> ActivityPin | None:
    return (
        db.query(ActivityPin)
        .filter(
            ActivityPin.tenant_id == ctx.tenant_id,
            ActivityPin.user_id == ctx.user.id,
            ActivityPin.project_id == activity.project_id,
            ActivityPin.activity_external_id == activity.external_id,
        )
        .first()
    )


@router.put("/activities/{activity_id}/pin", response_model=PinOut)
def pin_activity(
    activity_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(_ROLE),
) -> PinOut:
    activity = _activity(db, ctx, activity_id)
    pin = _pin_for(db, ctx, activity)
    if pin is None:
        snap = pin_snapshot(db, activity)
        pin = ActivityPin(
            id=uuid.uuid4(),
            tenant_id=ctx.tenant_id,
            project_id=activity.project_id,
            user_id=ctx.user.id,
            activity_external_id=activity.external_id,
            activity_name=activity.name,
            pinned_finish=snap["finish"],
            pinned_total_float_hours=snap["total_float_hours"],
            pinned_hours_per_day=snap["hours_per_day"],
            pinned_revision_label=snap["revision_label"],
        )
        db.add(pin)
        db.commit()
        db.refresh(pin)
    project = db.get(Project, activity.project_id)
    return build_pins(db, ctx, [pin], {project.id: project})[0]


@router.delete("/activities/{activity_id}/pin", status_code=204)
def unpin_activity(
    activity_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(_ROLE),
) -> None:
    activity = _activity(db, ctx, activity_id)
    pin = _pin_for(db, ctx, activity)
    if pin is not None:
        db.delete(pin)
        db.commit()


@router.delete("/pins/{pin_id}", status_code=204)
def delete_pin(
    pin_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(_ROLE),
) -> None:
    """By pin id — for a pin whose activity left the programme."""
    pin = get_tenant_scoped_or_404(db, ActivityPin, pin_id, ctx)
    if pin.user_id != ctx.user.id:
        raise HTTPException(status_code=404, detail="ActivityPin not found")
    db.delete(pin)
    db.commit()


@router.get("/activities/{activity_id}", response_model=ActivityDeskOut)
def get_activity_desk(
    activity_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(_ROLE),
) -> ActivityDeskOut:
    activity = _activity(db, ctx, activity_id)
    notes = (
        db.query(PersonalNote)
        .filter(
            PersonalNote.tenant_id == ctx.tenant_id,
            PersonalNote.user_id == ctx.user.id,
            PersonalNote.project_id == activity.project_id,
            PersonalNote.activity_external_id == activity.external_id,
        )
        .all()
    )
    projects = {activity.project_id: db.get(Project, activity.project_id)}
    return ActivityDeskOut(
        pinned=_pin_for(db, ctx, activity) is not None,
        notes=[note_out(n, projects) for n in sort_notes(notes)],
    )


# ---------------------------------------------------------------- notes


@router.get("/notes", response_model=list[NoteOut])
def list_notes(
    project_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(_ROLE),
) -> list[NoteOut]:
    """The caller's notes on one project (or every visible one), plus their
    general notes, which belong to no project."""
    projects = {p.id: p for p in _projects(db, ctx, project_id)}
    notes = (
        db.query(PersonalNote)
        .filter(
            PersonalNote.tenant_id == ctx.tenant_id,
            PersonalNote.user_id == ctx.user.id,
            PersonalNote.project_id.is_(None) | PersonalNote.project_id.in_(list(projects)),
        )
        .all()
    )
    return [note_out(n, projects) for n in sort_notes(notes)]


@router.post("/notes", response_model=NoteOut, status_code=201)
def create_note(
    payload: NoteCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(_ROLE),
) -> NoteOut:
    note = PersonalNote(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        user_id=ctx.user.id,
        body=payload.body,
        remind_on=payload.remind_on,
    )
    if payload.activity_id is not None:
        activity = _activity(db, ctx, payload.activity_id)
        snap = pin_snapshot(db, activity)
        note.project_id = activity.project_id
        note.activity_external_id = activity.external_id
        note.activity_name = activity.name
        note.context = {**snap, "finish": snap["finish"].isoformat() if snap["finish"] else None}
    elif payload.project_id is not None:
        _projects(db, ctx, payload.project_id)
        note.project_id = payload.project_id
    db.add(note)
    db.commit()
    db.refresh(note)
    return note_out(note, _project_map(db, ctx))


@router.patch("/notes/{note_id}", response_model=NoteOut)
def update_note(
    note_id: uuid.UUID,
    payload: NoteUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(_ROLE),
) -> NoteOut:
    note = _own_note(db, ctx, note_id)
    if payload.body is not None:
        note.body = payload.body
    # Sent as null, remind_on clears the reminder; left out, it stays.
    if "remind_on" in payload.model_fields_set:
        note.remind_on = payload.remind_on
    if payload.done is not None:
        note.done_at = datetime.now(timezone.utc) if payload.done else None
    db.commit()
    db.refresh(note)
    return note_out(note, _project_map(db, ctx))


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(
    note_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(_ROLE),
) -> None:
    db.delete(_own_note(db, ctx, note_id))
    db.commit()
