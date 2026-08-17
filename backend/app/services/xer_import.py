"""Imports a parsed, CPM-scheduled .xer file into the live activities/
activity_relationships tables. Runs inside the caller's already-RLS-scoped
session — no BYPASSRLS needed, since this only ever runs under an
authenticated tenant request (see api/routes/schedule_imports.py).

Field-ownership policy on UPDATE (an activity that already exists, matched by
external_id/task_code within the project):
  - P6-native fields (target/remaining duration, calendar, task/status code,
    dates, float, criticality, constraints) are overwritten wholesale — the
    .xer file is the source of truth for the schedule logic.
  - Subcontractor-owned fields (`percent_complete`, `actual_start`,
    `actual_finish`, `status`, `remaining_duration_days`) are left untouched —
    those are edited via the existing PATCH /activities/{id} endpoint during
    an open UpdatePeriod (see api/routes/activities.py::update_activity) and
    must survive a schedule re-import.
On CREATE (no existing row for that external_id), every field is populated
from the import, including the subcontractor-owned ones (best available P6
data — physical % complete, actual dates, remaining duration converted to
days).

Relationships are matched by P6's internal `task_id` (not the human-readable
`task_code` we store as `external_id`) — that's what TASKPRED rows reference.
Since a .xer export is always a full network snapshot, relationships are
replaced wholesale on every import rather than diffed.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.deps import AuthContext
from app.engine.cpm.scheduler import schedule
from app.models.activity import Activity, ActivityStatus
from app.models.activity_relationship import ActivityRelationship, LinkType
from app.models.calendar import Calendar as CalendarModel
from app.models.schedule_import import ScheduleImport
from app.parser.xer_models import ParsedSchedule
from app.parser.xer_parser import parse_xer

_TOL = 0.01

_PRED_TYPE_TO_LINK_TYPE = {
    "PR_FS": LinkType.FS,
    "PR_SS": LinkType.SS,
    "PR_FF": LinkType.FF,
    "PR_SF": LinkType.SF,
}


def _to_date(dt: datetime | None) -> date | None:
    return dt.date() if dt else None


def _derive_status(status_code: str, phys_complete_pct: float) -> tuple[ActivityStatus, int]:
    """Map P6's status_code/phys_complete_pct onto our simplified ActivityStatus +
    percent_complete (0-100 int) — used only when CREATING a new activity row."""
    pct = max(0, min(100, round(phys_complete_pct)))
    if status_code == "TK_Complete":
        return ActivityStatus.complete, 100
    if status_code == "TK_Active" or pct > 0:
        return ActivityStatus.in_progress, pct
    return ActivityStatus.not_started, pct


def import_xer(
    db: Session, project_id: uuid.UUID, ctx: AuthContext, filename: str, file_bytes: bytes
) -> ScheduleImport:
    parsed: ParsedSchedule = parse_xer(file_bytes)
    schedule(parsed)

    import_id = uuid.uuid4()

    # --- calendars: upsert by (project_id, clndr_id) ---
    existing_calendars = {
        c.clndr_id: c for c in db.query(CalendarModel).filter(CalendarModel.project_id == project_id).all()
    }
    clndr_id_to_row_id: dict[str, uuid.UUID] = {}
    for cal in parsed.calendars:
        row = existing_calendars.get(cal.clndr_id)
        work_week = [
            {
                "day_of_week": d.day_of_week,
                "shifts": [{"start": s.start.isoformat(), "end": s.end.isoformat()} for s in d.shifts],
            }
            for d in cal.default_work_week
        ]
        exceptions = [
            {
                "exc_date": e.exc_date.isoformat(),
                "shifts": [{"start": s.start.isoformat(), "end": s.end.isoformat()} for s in e.shifts],
            }
            for e in cal.exceptions
        ]
        if row is None:
            row = CalendarModel(
                id=uuid.uuid4(),
                tenant_id=ctx.tenant_id,
                project_id=project_id,
                clndr_id=cal.clndr_id,
                name=cal.clndr_name,
                hours_per_day=cal.hours_per_day,
                work_week=work_week,
                exceptions=exceptions,
            )
            db.add(row)
        else:
            row.name = cal.clndr_name
            row.hours_per_day = cal.hours_per_day
            row.work_week = work_week
            row.exceptions = exceptions
        db.flush()
        clndr_id_to_row_id[cal.clndr_id] = row.id

    default_calendar_row_id = clndr_id_to_row_id.get(parsed.meta.clndr_id or "") or (
        next(iter(clndr_id_to_row_id.values())) if clndr_id_to_row_id else None
    )

    # --- activities: upsert by (project_id, external_id==task_code) ---
    existing_activities = {a.external_id: a for a in db.query(Activity).filter(Activity.project_id == project_id).all()}
    task_id_to_row_id: dict[str, uuid.UUID] = {}
    critical_count = 0

    for act in parsed.activities:
        row = existing_activities.get(act.task_code)
        is_new = row is None
        if row is None:
            row = Activity(
                id=uuid.uuid4(),
                tenant_id=ctx.tenant_id,
                project_id=project_id,
                external_id=act.task_code,
                discipline="General",
                status=ActivityStatus.not_started,
            )
            db.add(row)

        row.name = act.task_name
        row.clndr_id = clndr_id_to_row_id.get(act.clndr_id or "", default_calendar_row_id)
        row.wbs_path = act.wbs_id
        row.task_type = act.task_type
        row.status_code = act.status_code
        row.target_duration_hours = act.target_drtn_hr_cnt
        row.remaining_duration_hours = act.remain_drtn_hr_cnt
        row.planned_start = _to_date(act.target_start_date)
        row.planned_finish = _to_date(act.target_end_date)
        row.early_start = _to_date(act.early_start_date)
        row.early_finish = _to_date(act.early_end_date)
        row.late_start = _to_date(act.late_start_date)
        row.late_finish = _to_date(act.late_end_date)
        row.total_float_hours = act.total_float_hr_cnt
        row.free_float_hours = act.free_float_hr_cnt
        is_critical = act.total_float_hr_cnt is not None and act.total_float_hr_cnt <= _TOL
        row.is_critical = is_critical
        row.constraint_type = act.cstr_type
        row.constraint_date = _to_date(act.cstr_date)
        row.constraint_type_2 = act.cstr_type2
        row.constraint_date_2 = _to_date(act.cstr_date2)
        row.is_longest_path = act.lp_critical
        row.last_import_id = import_id

        if is_critical:
            critical_count += 1

        if is_new:
            status, pct = _derive_status(act.status_code, act.phys_complete_pct)
            row.status = status
            row.percent_complete = pct
            row.actual_start = _to_date(act.act_start_date)
            row.actual_finish = _to_date(act.act_end_date)
            row.remaining_duration_days = round(act.remain_drtn_hr_cnt / 8.0)
        # else: percent_complete/actual_start/actual_finish/status/remaining_duration_days
        # are left untouched — subcontractor-owned, see module docstring.

        db.flush()
        task_id_to_row_id[act.task_id] = row.id

    # --- relationships: the .xer is a full network snapshot, so replace wholesale ---
    db.query(ActivityRelationship).filter(ActivityRelationship.project_id == project_id).delete()
    for rel in parsed.relationships:
        pred_row_id = task_id_to_row_id.get(rel.pred_task_id)
        succ_row_id = task_id_to_row_id.get(rel.task_id)
        if pred_row_id is None or succ_row_id is None:
            continue
        db.add(
            ActivityRelationship(
                id=uuid.uuid4(),
                tenant_id=ctx.tenant_id,
                project_id=project_id,
                predecessor_id=pred_row_id,
                successor_id=succ_row_id,
                link_type=_PRED_TYPE_TO_LINK_TYPE.get(rel.pred_type, LinkType.FS),
                lag_days=round(rel.lag_hr_cnt / 8.0),
                lag_hours=round(rel.lag_hr_cnt),
            )
        )

    schedule_import = ScheduleImport(
        id=import_id,
        tenant_id=ctx.tenant_id,
        project_id=project_id,
        filename=filename,
        data_date=parsed.meta.data_date,
        imported_by_user_id=ctx.user.id,
        activity_count=len(parsed.activities),
        critical_count=critical_count,
        warnings=parsed.parse_log,
    )
    db.add(schedule_import)

    db.commit()
    db.refresh(schedule_import)
    return schedule_import
