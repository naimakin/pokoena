import uuid
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission
from app.engine.cpm.calendar_engine import CalendarEngine
from app.engine.cpm.float_path import (
    DEFAULT_PATH_COUNT,
    MAX_PATH_COUNT,
    Method,
    WorkDays,
    compute_float_paths,
)
from app.engine.durations import DEFAULT_HOURS_PER_DAY, activity_days, valid_hours_per_day
from app.engine.evm.evm_engine import build_calendar_engine
from app.models.activity import Activity
from app.models.activity_relationship import ActivityRelationship
from app.models.calendar import Calendar
from app.models.project import Project
from app.schemas.float_path import FloatPathEndCandidateOut, FloatPathReportOut
from app.services.schedule_current import get_current_import, to_naive

router = APIRouter(prefix="/projects/{project_id}/float-path", tags=["float-path"])

# WBS summary rows are rollups, not work — they are never the end of a float
# path and never drive anything.
_EXCLUDED_TASK_TYPE = "TT_WBS"
_MILESTONE_TYPES = ("TT_Mile", "TT_FinMile")
# Sorts undated activities last rather than blowing up on a None comparison.
_FAR_FUTURE = date(9999, 12, 31)


def _calendars(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> list[Calendar]:
    return (
        db.query(Calendar).filter(Calendar.tenant_id == tenant_id, Calendar.project_id == project_id).all()
    )


def _hours_per_day(calendars: list[Calendar]) -> float:
    """Only the fallback for an activity with no calendar of its own — every
    activity's hours read in days on ITS calendar (engine/durations.py)."""
    for cal in calendars:
        if cal.hours_per_day:
            return cal.hours_per_day
    return DEFAULT_HOURS_PER_DAY


def _work_days_fn(calendars: list[Calendar]) -> WorkDays | None:
    """Working days between two dates on an activity's own calendar. Without
    this a link that only spans a weekend reads as slack it does not have.

    Engines are cached per calendar because a float path walk asks this
    question once per candidate relationship, which on a real programme is
    thousands of times."""
    # Keyed by calendars.id, because that is what Activity.clndr_id holds (the
    # P6 clndr_id string lives on the row as a separate column).
    engines: dict[str, CalendarEngine] = {}
    hpd_by_id = {str(cal.id): valid_hours_per_day(cal.hours_per_day) for cal in calendars}
    for cal in calendars:
        try:
            engines[str(cal.id)] = build_calendar_engine(cal)
        except Exception:  # a blank or unparseable calendar — no worse than no calendar
            continue
    if not engines:
        return None

    fallback = engines[str(calendars[0].id)] if str(calendars[0].id) in engines else next(iter(engines.values()))
    hours_per_day = _hours_per_day(calendars)

    def work_days(start: date, end: date, clndr_id: str | None) -> float:
        engine = engines.get(str(clndr_id), fallback)
        hpd = hpd_by_id.get(str(clndr_id), hours_per_day)
        try:
            hours = engine.work_hours_between(datetime.combine(start, time()), datetime.combine(end, time()))
        except Exception:
            # A calendar with no working days in the window. Fall back to plain
            # days for this one link rather than failing the whole analysis.
            return float((end - start).days)
        return hours / hpd

    return work_days


def _load(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> tuple[list[Activity], list[ActivityRelationship]]:
    """Activities on the current programme plus the relationships between them.

    Scoped to the current import for the same reason `routes/activities.py`
    is: rows left behind by a superseded programme would otherwise show up as
    predecessors that are not in the schedule any more."""
    query = db.query(Activity).filter(Activity.tenant_id == tenant_id, Activity.project_id == project_id)
    current_import = get_current_import(db, tenant_id, project_id)
    if current_import is not None:
        query = query.filter(
            (Activity.last_import_id.is_(None)) | (Activity.last_import_id == current_import.id)
        )
    activities = [a for a in query.all() if (a.task_type or "") != _EXCLUDED_TASK_TYPE]

    known = {a.id for a in activities}
    relationships = [
        r
        for r in db.query(ActivityRelationship)
        .filter(
            ActivityRelationship.tenant_id == tenant_id,
            ActivityRelationship.project_id == project_id,
        )
        .all()
        if r.predecessor_id in known and r.successor_id in known
    ]
    return activities, relationships


@router.get("/end-candidates", response_model=list[FloatPathEndCandidateOut])
def list_end_candidates(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> list[FloatPathEndCandidateOut]:
    """What a planner can run a float path to. Milestones first (that is what
    the analysis is usually run against), then every other activity, each
    ordered by finish date."""
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)

    activities, _rels = _load(db, ctx.tenant_id, project_id)

    rows = sorted(
        activities,
        key=lambda a: (
            0 if (a.task_type or "") in _MILESTONE_TYPES else 1,
            a.early_finish or a.planned_finish or _FAR_FUTURE,
            a.external_id,
        ),
    )
    return [
        FloatPathEndCandidateOut(
            external_id=a.external_id,
            name=a.name,
            task_type=a.task_type,
            early_finish=a.early_finish or a.planned_finish,
            total_float_days=(
                round(activity_days(a, a.total_float_hours), 2) if a.total_float_hours is not None else None
            ),
            is_critical=bool(a.is_critical),
        )
        for a in rows
    ]


@router.get("", response_model=FloatPathReportOut)
def get_float_paths(
    project_id: uuid.UUID,
    end_activity: str = Query(..., description="external_id of the activity the paths end at"),
    method: Method = Query(default="free_float"),
    path_count: int = Query(default=DEFAULT_PATH_COUNT, ge=1, le=MAX_PATH_COUNT),
    exclude_completed: bool = Query(default=True),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> FloatPathReportOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)

    activities, relationships = _load(db, ctx.tenant_id, project_id)
    by_id = {a.id: a for a in activities}
    calendars = _calendars(db, ctx.tenant_id, project_id)
    hours_per_day = _hours_per_day(calendars)

    act_payload = [
        {
            "external_id": a.external_id,
            "clndr_id": str(a.clndr_id) if a.clndr_id else None,
            "name": a.name,
            "wbs_path": a.wbs_path,
            "status": a.status.value if a.status else None,
            "percent_complete": a.percent_complete,
            "early_start": a.early_start or a.planned_start,
            "early_finish": a.early_finish or a.planned_finish,
            "late_start": a.late_start,
            "late_finish": a.late_finish,
            "total_float_hours": a.total_float_hours,
            "free_float_hours": a.free_float_hours,
            "is_critical": a.is_critical,
            "is_longest_path": a.is_longest_path,
            "hours_per_day": a.hours_per_day,
        }
        for a in activities
    ]
    rel_payload = [
        {
            "pred_external_id": by_id[r.predecessor_id].external_id,
            "succ_external_id": by_id[r.successor_id].external_id,
            "link_type": r.link_type.value if r.link_type else "FS",
            "lag_days": r.lag_days,
        }
        for r in relationships
    ]

    try:
        result = compute_float_paths(
            act_payload,
            rel_payload,
            end_activity,
            method=method,
            path_count=path_count,
            hours_per_day=hours_per_day,
            work_days=_work_days_fn(calendars),
            exclude_completed=exclude_completed,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No activity {end_activity} on the current programme")

    current_import = get_current_import(db, ctx.tenant_id, project_id)
    end_row = next((a for a in activities if a.external_id == end_activity), None)

    return FloatPathReportOut(
        project_id=project_id,
        data_date=to_naive(current_import.data_date) if current_import else None,
        revision_label=current_import.revision_label if current_import else None,
        end_activity_external_id=result.end_activity_external_id,
        end_activity_name=end_row.name if end_row else None,
        method=result.method,
        requested_paths=result.requested_paths,
        hours_per_day=hours_per_day,
        truncated=result.truncated,
        acceleration_headroom_days=result.acceleration_headroom_days,
        paths=result.paths,
    )
