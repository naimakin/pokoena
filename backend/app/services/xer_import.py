"""Imports a parsed, CPM-scheduled .xer file into the live activities/
activity_relationships tables. Runs inside the caller's already-RLS-scoped
session — no BYPASSRLS needed, since this only ever runs under an
authenticated tenant request (see api/routes/schedule_imports.py).

Field-ownership policy on UPDATE (an activity that already exists, matched by
external_id/task_code within the project):
  - P6-native fields (target/remaining duration, calendar, task/status code,
    dates, float, criticality, constraints) are overwritten wholesale — the
    .xer file is the source of truth for the schedule logic.
  - Progress fields (`percent_complete`, `actual_start`, `actual_finish`,
    `status`, `remaining_duration_days`) are also edited in Poko (PATCH
    /activities, see api/routes/activities.py). They take P6's values whenever
    the file is at least as far along as Poko — the normal case, since the
    round-trip carries Poko's progress into P6 and back — and keep Poko's only
    when Poko is AHEAD: progress recorded in the field after the file left for
    P6, which a re-import must not wipe. See `_p6_progress_wins`.
    (Keeping Poko's unconditionally, the earlier rule, froze every activity at
    whatever the FIRST import said: upload a baseline, then an update, and
    everything the update had completed still read "Not Started".)
On CREATE (no existing row for that external_id), every field is populated
from the import (best available P6 data — physical % complete, actual dates,
remaining duration converted to days).

Relationships are matched by P6's internal `task_id` (not the human-readable
`task_code` we store as `external_id`) — that's what TASKPRED rows reference.
Since a .xer export is always a full network snapshot, the live
`activity_relationships` rows are replaced wholesale on every import rather
than diffed in place. A frozen copy of that import's relationships (keyed by
external_id, since that survives re-imports) is written to
`ScheduleImport.relationships_snapshot` so two imports of the same project
can later be compared — see `engine/diff/logic_diff.py`.
"""

from __future__ import annotations

import gzip
import uuid
from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.deps import AuthContext
from app.engine.cpm.scheduler import schedule
from app.models.activity import Activity, ActivityStatus
from app.models.activity_code import ActivityCodeType, ActivityCodeValue, TaskActivityCode
from app.models.activity_relationship import ActivityRelationship, LinkType
from app.models.calendar import Calendar as CalendarModel
from app.models.project import Project
from app.models.resource import Resource as ResourceModel
from app.models.resource_assignment import ResourceAssignment as ResourceAssignmentModel
from app.models.recovery_plan import RecoveryPlan
from app.models.schedule_import import ScheduleImport
from app.models.schedule_status_snapshot import ScheduleStatusSnapshot
from app.models.wbs_node import WbsNode
from app.parser.xer_models import ParsedSchedule
from app.parser.xer_parser import parse_xer
from app.models.baseline import Baseline, BaselineStatus
from app.services.baseline import (
    BaselineLockError,
    lock_baseline_for_project,
    lock_baseline_from_parsed,
    overwrite_active_baseline_from_parsed,
    unique_baseline_label,
)
from app.services.activity_progress import apply_units_from_progress, clear_float_if_finished
from app.services.project_status import compute_status_rollup
from app.services.schedule_current import get_current_import, mark_current, to_naive

_TOL = 0.01

_PRED_TYPE_TO_LINK_TYPE = {
    "PR_FS": LinkType.FS,
    "PR_SS": LinkType.SS,
    "PR_FF": LinkType.FF,
    "PR_SF": LinkType.SF,
}


def _to_date(dt: datetime | None) -> date | None:
    return dt.date() if dt else None


class DataDateRegressionError(ValueError):
    """Raised when an import's data date is older than the project's current
    live schedule's — importing it would move activity dates/progress
    backward, almost always an accidental upload of a stale file (e.g. an old
    baseline re-uploaded after a newer update programme already came in).
    Callers pass force=True to import anyway."""

    def __init__(self, new_data_date: datetime, current_data_date: datetime):
        self.new_data_date = new_data_date
        self.current_data_date = current_data_date
        super().__init__(
            f"This file's data date ({new_data_date.date()}) is older than the project's current "
            f"data date ({current_data_date.date()}) — importing it will move the live schedule backward."
        )


def _is_critical(total_float_hr_cnt: float | None, status_code: str, act_end_date: datetime | None) -> bool:
    """Critical = an unfinished activity whose total float is zero or negative.

    An activity with an actual finish (act_end_date) — or P6's TK_Complete
    status — has no remaining work to protect, so it's never critical whatever
    total float the CPM run reports for it (the scheduler pins finished tasks
    to 0.0 for display); this matches P6's own critical filter. An empty total
    float is never critical either (P6 leaves it blank for finished work)."""
    if act_end_date is not None or status_code == "TK_Complete":
        return False
    return total_float_hr_cnt is not None and total_float_hr_cnt <= _TOL


def _derive_status(status_code: str, phys_complete_pct: float) -> tuple[ActivityStatus, int]:
    """Map P6's status_code/phys_complete_pct onto our simplified ActivityStatus +
    percent_complete (0-100 int) — used only when CREATING a new activity row."""
    pct = max(0, min(100, round(phys_complete_pct)))
    if status_code == "TK_Complete":
        return ActivityStatus.complete, 100
    if status_code == "TK_Active" or pct > 0:
        return ActivityStatus.in_progress, pct
    return ActivityStatus.not_started, pct


_STATUS_RANK = {ActivityStatus.not_started: 0, ActivityStatus.in_progress: 1, ActivityStatus.complete: 2}


def _p6_progress_wins(row: Activity, p6_status: ActivityStatus, p6_pct: int) -> bool:
    """Whether an existing activity takes the file's progress. Ties go to P6:
    same status and % means the file came back through P6, whose actual dates
    are then the authoritative ones."""
    poko = (_STATUS_RANK.get(row.status, 0), int(row.percent_complete or 0))
    return (_STATUS_RANK[p6_status], p6_pct) >= poko


def import_xer(
    db: Session,
    project_id: uuid.UUID,
    ctx: AuthContext,
    filename: str,
    file_bytes: bytes,
    *,
    revision_kind: str = "update",
    roundtrip_from_export_id: uuid.UUID | None = None,
    force: bool = False,
    reuse_import: ScheduleImport | None = None,
) -> ScheduleImport:
    """`revision_kind` drives the sync-log label: "update" (Program Library)
    gets the next per-project UPD-n; "baseline" (Planning → Baselines) and the
    project's very first upload are the unnumbered "Baseline programme".

    `force=False` (the default) raises DataDateRegressionError instead of
    importing when the file's data date is older than the project's current
    one — every "update" import overwrites the live activities/relationships
    tables wholesale (see module docstring), so an out-of-order upload would
    otherwise silently regress live progress. A "baseline" upload onto a
    project that already has its own current data (i.e. not the project's
    very first import) never touches the live tables at all — see
    `baseline_non_destructive` below — so this check doesn't apply to it and
    is skipped; the baseline's own (usually older) data date is expected.

    `reuse_import` re-applies an earlier import's stored .xer to the live tables
    ("Current update" re-pointed in Program Library): no new ScheduleImport row,
    no regression check (the user chose it), no relabel / auto-baseline / status
    snapshot — that import keeps the metadata and frozen snapshots it already has;
    it just becomes the current one again."""
    parsed: ParsedSchedule = parse_xer(file_bytes)
    schedule(parsed)

    is_first_import = db.query(ScheduleImport).filter(ScheduleImport.project_id == project_id).first() is None
    # A baseline programme upload (Planning -> Baselines) never touches the
    # live schedule once the project already has its own current data — only
    # a project's very first upload (there IS no separate "current" yet)
    # still imports into the live tables the normal way. This is what stops
    # re-uploading/replacing the baseline from silently overwriting "Current
    # update" with the baseline's own (usually older, often smaller-scope)
    # data — the bug that made Dashboard/WBS/Gantt/etc. show baseline data.
    baseline_non_destructive = revision_kind == "baseline" and not is_first_import and reuse_import is None

    if not force and not baseline_non_destructive and reuse_import is None and parsed.meta.data_date is not None:
        current = get_current_import(db, ctx.tenant_id, project_id)
        current_data_date = to_naive(current.data_date) if current is not None else None
        if current_data_date is not None and parsed.meta.data_date < current_data_date:
            raise DataDateRegressionError(parsed.meta.data_date, current_data_date)

    import_id = reuse_import.id if reuse_import is not None else uuid.uuid4()

    # Created (and flushed) up front, not at the end: activities below stamp
    # last_import_id=import_id and get flushed per-row as they're upserted,
    # and that column is a real FK to schedule_imports.id — inserting an
    # activity before this row exists violates the constraint on Postgres
    # (SQLite, what the test suite runs against, doesn't enforce FKs by
    # default, so this only ever surfaced against a real Postgres import).
    # Its summary fields (activity_count, etc.) are filled in on this same
    # tracked instance at the end, once they're known.
    if reuse_import is not None:
        schedule_import = reuse_import
    else:
        schedule_import = ScheduleImport(
            id=import_id,
            tenant_id=ctx.tenant_id,
            project_id=project_id,
            filename=filename,
            data_date=parsed.meta.data_date,
            imported_by_user_id=ctx.user.id,
            roundtrip_from_export_id=roundtrip_from_export_id,
            # Kept so "Current update" can later be re-pointed at this import.
            source_file=gzip.compress(file_bytes),
            has_source_file=True,
        )
        db.add(schedule_import)
        db.flush()

    if not baseline_non_destructive:
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

        # --- P6 project identity: needed to write a re-importable PROJECT row on
        # export (engine/export/xer_writer.py) — see that module for why matching
        # P6's own proj_id matters for the download-F9-reupload workflow. ---
        project = db.get(Project, project_id)
        project.p6_proj_id = parsed.meta.proj_id or project.p6_proj_id
        project.p6_proj_short_name = parsed.meta.proj_short_name or project.p6_proj_short_name

        # --- WBS nodes: upsert by (project_id, wbs_id), then delete whatever
        # existed before but isn't part of THIS import (excluding manually-added
        # nodes, wbs_id "manual-…" — see api/routes/wbs.py). The .xer is a full WBS
        # snapshot, same as relationships/resource assignments below: without this,
        # uploading a different program (or a P6 project whose root WBS id changed
        # across revisions) left its old WBS tree behind forever, shown alongside
        # the new one on Planning > WBS with no way to tell which was current.
        # ScheduleImport.wbs_snapshot (below) is what still lets an earlier
        # program's WBS be viewed on request once this table has moved on. ---
        existing_wbs = {n.wbs_id: n for n in db.query(WbsNode).filter(WbsNode.project_id == project_id).all()}
        incoming_wbs_ids = {node.wbs_id for node in parsed.wbs_nodes}
        for node in parsed.wbs_nodes:
            wbs_row = existing_wbs.get(node.wbs_id)
            if wbs_row is None:
                wbs_row = WbsNode(
                    id=uuid.uuid4(), tenant_id=ctx.tenant_id, project_id=project_id, wbs_id=node.wbs_id
                )
                db.add(wbs_row)
            wbs_row.parent_wbs_id = node.parent_wbs_id
            wbs_row.wbs_short_name = node.wbs_short_name
            wbs_row.wbs_name = node.wbs_name
            wbs_row.seq_num = node.seq_num
        db.query(WbsNode).filter(
            WbsNode.project_id == project_id,
            WbsNode.wbs_id.notin_(incoming_wbs_ids),
            ~WbsNode.wbs_id.startswith("manual-"),
        ).delete(synchronize_session=False)

        # --- activities: upsert by (project_id, external_id==task_code), falling
        # back to P6's internal task_id so an Activity-ID rename in P6 stays an
        # UPDATE (preserving user-entered actual dates / % / status) instead of a
        # delete + recreate that would silently drop those edits. ---
        _all_activities = db.query(Activity).filter(Activity.project_id == project_id).all()
        existing_activities = {a.external_id: a for a in _all_activities}
        existing_by_p6_task_id = {a.p6_task_id: a for a in _all_activities if a.p6_task_id}
        task_id_to_row_id: dict[str, uuid.UUID] = {}
        critical_count = 0
        incoming_task_codes = {a.task_code for a in parsed.activities}
        # Frozen per-activity finish/criticality/status for "vs previous UPD" slip
        # comparison (engine/diff/slip_diff.py) — the live table is overwritten each
        # import so this is the only history.
        activities_snapshot: list[dict] = []
        renamed_external_ids: list[tuple[str, str]] = []  # (old, new) for recovery-plan re-linking
        poko_ahead: dict[uuid.UUID, Activity] = {}

        for act in parsed.activities:
            row = existing_activities.get(act.task_code)
            if row is None and act.task_id:
                renamed = existing_by_p6_task_id.get(act.task_id)
                # Only treat it as a rename when the old code isn't itself still in
                # this import (i.e. it really went away, not just got reassigned).
                if renamed is not None and renamed.external_id not in incoming_task_codes:
                    row = renamed
                    renamed_external_ids.append((row.external_id, act.task_code))
                    row.external_id = act.task_code
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
            is_critical = _is_critical(act.total_float_hr_cnt, act.status_code, act.act_end_date)
            row.is_critical = is_critical
            row.constraint_type = act.cstr_type
            row.constraint_date = _to_date(act.cstr_date)
            row.constraint_type_2 = act.cstr_type2
            row.constraint_date_2 = _to_date(act.cstr_date2)
            row.is_longest_path = act.lp_critical
            row.last_import_id = import_id
            row.p6_task_id = act.task_id

            if is_critical:
                critical_count += 1

            status, pct = _derive_status(act.status_code, act.phys_complete_pct)
            if is_new or _p6_progress_wins(row, status, pct):
                row.status = status
                row.percent_complete = pct
                row.actual_start = _to_date(act.act_start_date)
                row.actual_finish = _to_date(act.act_end_date)
                row.remaining_duration_days = round(act.remain_drtn_hr_cnt / 8.0)
            else:
                # Poko is ahead of the file — keep its progress (module docstring),
                # and bring the units of this activity's assignments in line
                # with it once they're rebuilt from the file below.
                poko_ahead[row.id] = row
                clear_float_if_finished(row)
                if is_critical and not row.is_critical:
                    critical_count -= 1

            db.flush()
            task_id_to_row_id[act.task_id] = row.id
            activities_snapshot.append(
                {
                    "external_id": row.external_id,
                    "p6_task_id": row.p6_task_id,
                    "name": row.name,
                    "wbs_path": row.wbs_path,
                    "task_type": row.task_type,
                    "planned_start": row.planned_start.isoformat() if row.planned_start else None,
                    "planned_finish": row.planned_finish.isoformat() if row.planned_finish else None,
                    "early_start": row.early_start.isoformat() if row.early_start else None,
                    "early_finish": row.early_finish.isoformat() if row.early_finish else None,
                    "actual_start": row.actual_start.isoformat() if row.actual_start else None,
                    "actual_finish": row.actual_finish.isoformat() if row.actual_finish else None,
                    "target_duration_hours": row.target_duration_hours,
                    "remaining_duration_hours": row.remaining_duration_hours,
                    "constraint_type": row.constraint_type,
                    "constraint_date": row.constraint_date.isoformat() if row.constraint_date else None,
                    "is_critical": bool(row.is_critical),
                    "is_longest_path": bool(row.is_longest_path),
                    "total_float_hours": row.total_float_hours,
                    "status": row.status.value,
                    "percent_complete": int(row.percent_complete or 0),
                }
            )

        # Re-link any recovery plans whose activity was renamed in P6 so their
        # durable key (activity_external_id) keeps pointing at the same activity.
        for old_code, new_code in renamed_external_ids:
            db.query(RecoveryPlan).filter(
                RecoveryPlan.project_id == project_id,
                RecoveryPlan.activity_external_id == old_code,
            ).update({RecoveryPlan.activity_external_id: new_code}, synchronize_session=False)

        # --- relationships: the .xer is a full network snapshot, so replace wholesale ---
        db.query(ActivityRelationship).filter(ActivityRelationship.project_id == project_id).delete()
        acts_by_task_id = {a.task_id: a for a in parsed.activities}
        relationships_snapshot: list[dict] = []
        for rel in parsed.relationships:
            pred_row_id = task_id_to_row_id.get(rel.pred_task_id)
            succ_row_id = task_id_to_row_id.get(rel.task_id)
            if pred_row_id is None or succ_row_id is None:
                continue
            link_type = _PRED_TYPE_TO_LINK_TYPE.get(rel.pred_type, LinkType.FS)
            db.add(
                ActivityRelationship(
                    id=uuid.uuid4(),
                    tenant_id=ctx.tenant_id,
                    project_id=project_id,
                    predecessor_id=pred_row_id,
                    successor_id=succ_row_id,
                    link_type=link_type,
                    lag_days=round(rel.lag_hr_cnt / 8.0),
                    lag_hours=round(rel.lag_hr_cnt),
                )
            )

            # Frozen for Logic Diff (engine/diff/logic_diff.py) — captured here
            # (not re-derived from the DB later) so criticality reflects this
            # import's own CPM result, not whatever the live rows say afterward.
            pred_act = acts_by_task_id.get(rel.pred_task_id)
            succ_act = acts_by_task_id.get(rel.task_id)
            relationships_snapshot.append(
                {
                    "pred_external_id": pred_act.task_code if pred_act else rel.pred_task_id,
                    "pred_name": pred_act.task_name if pred_act else "",
                    "succ_external_id": succ_act.task_code if succ_act else rel.task_id,
                    "succ_name": succ_act.task_name if succ_act else "",
                    "link_type": link_type.value,
                    "lag_hours": rel.lag_hr_cnt,
                    "pred_critical": bool(
                        pred_act and _is_critical(pred_act.total_float_hr_cnt, pred_act.status_code, pred_act.act_end_date)
                    ),
                    "succ_critical": bool(
                        succ_act and _is_critical(succ_act.total_float_hr_cnt, succ_act.status_code, succ_act.act_end_date)
                    ),
                }
            )

        # --- resources: upsert by (project_id, rsrc_id) — feeds the quick EVM engine
        # (engine/evm/evm_engine.py) and DCMA check #10. ---
        existing_resources = {
            r.rsrc_id: r for r in db.query(ResourceModel).filter(ResourceModel.project_id == project_id).all()
        }
        rsrc_id_to_row_id: dict[str, uuid.UUID] = {}
        for res in parsed.resources:
            res_row = existing_resources.get(res.rsrc_id)
            if res_row is None:
                res_row = ResourceModel(
                    id=uuid.uuid4(), tenant_id=ctx.tenant_id, project_id=project_id, rsrc_id=res.rsrc_id
                )
                db.add(res_row)
            res_row.name = res.rsrc_name
            res_row.short_name = res.rsrc_short_name
            res_row.rsrc_type = res.rsrc_type
            res_row.unit_id = res.unit_id
            res_row.clndr_id = res.clndr_id
            res_row.curr_id = res.curr_id
            db.flush()
            rsrc_id_to_row_id[res.rsrc_id] = res_row.id

        # --- resource assignments: replace wholesale per import, same as
        # relationships — a fresh import is the source of truth for resource loading. ---
        db.query(ResourceAssignmentModel).filter(ResourceAssignmentModel.project_id == project_id).delete()
        for assign in parsed.assignments:
            activity_row_id = task_id_to_row_id.get(assign.task_id)
            resource_row_id = rsrc_id_to_row_id.get(assign.rsrc_id)
            if activity_row_id is None or resource_row_id is None:
                continue
            assignment_row = ResourceAssignmentModel(
                id=uuid.uuid4(),
                tenant_id=ctx.tenant_id,
                project_id=project_id,
                activity_id=activity_row_id,
                resource_id=resource_row_id,
                remain_qty=assign.remain_qty,
                target_qty=assign.target_qty,
                act_reg_qty=assign.act_reg_qty,
                target_cost=assign.target_cost,
                act_reg_cost=assign.act_reg_cost,
                remain_cost=assign.remain_cost,
                unit_id=assign.unit_id,
            )
            if activity_row_id in poko_ahead:
                apply_units_from_progress(poko_ahead[activity_row_id], [assignment_row])
            db.add(assignment_row)

        # --- activity code types/values: upsert by (project_id, code_type_id) /
        # (project_id, actv_code_id) — same small-stable-tree pattern as WBS nodes. ---
        existing_code_types = {
            t.actv_code_type_id: t
            for t in db.query(ActivityCodeType).filter(ActivityCodeType.project_id == project_id).all()
        }
        code_type_id_to_row_id: dict[str, uuid.UUID] = {}
        for ct in parsed.code_types:
            ct_row = existing_code_types.get(ct.actv_code_type_id)
            if ct_row is None:
                ct_row = ActivityCodeType(
                    id=uuid.uuid4(), tenant_id=ctx.tenant_id, project_id=project_id,
                    actv_code_type_id=ct.actv_code_type_id,
                )
                db.add(ct_row)
            ct_row.name = ct.actv_code_type
            db.flush()
            code_type_id_to_row_id[ct.actv_code_type_id] = ct_row.id

        existing_code_values = {
            v.actv_code_id: v
            for v in db.query(ActivityCodeValue).filter(ActivityCodeValue.project_id == project_id).all()
        }
        code_value_id_to_row_id: dict[str, uuid.UUID] = {}
        for cv in parsed.code_values:
            code_type_row_id = code_type_id_to_row_id.get(cv.actv_code_type_id)
            if code_type_row_id is None:
                continue
            cv_row = existing_code_values.get(cv.actv_code_id)
            if cv_row is None:
                cv_row = ActivityCodeValue(
                    id=uuid.uuid4(), tenant_id=ctx.tenant_id, project_id=project_id,
                    code_type_id=code_type_row_id, actv_code_id=cv.actv_code_id,
                )
                db.add(cv_row)
            cv_row.code_type_id = code_type_row_id
            cv_row.name = cv.actv_code_name
            cv_row.short_name = cv.short_name
            cv_row.parent_actv_code_id = cv.parent_actv_code_id
            cv_row.seq_num = cv.seq_num
            db.flush()
            code_value_id_to_row_id[cv.actv_code_id] = cv_row.id

        # --- task activity codes: replace wholesale per import, same as
        # relationships/resource assignments. ---
        db.query(TaskActivityCode).filter(TaskActivityCode.project_id == project_id).delete()
        for tac in parsed.activity_codes:
            activity_row_id = task_id_to_row_id.get(tac.task_id)
            code_value_row_id = code_value_id_to_row_id.get(tac.actv_code_id)
            if activity_row_id is None or code_value_row_id is None:
                continue
            db.add(
                TaskActivityCode(
                    id=uuid.uuid4(), tenant_id=ctx.tenant_id, project_id=project_id,
                    activity_id=activity_row_id, code_value_id=code_value_row_id,
                )
            )
    else:
        # --- Non-destructive baseline path: build this import's historical
        # snapshot straight from the parsed file, field-for-field the same
        # shape as the destructive path above, but never touch WBS/Activity/
        # relationships/resources/activity-codes — those stay exactly as the
        # project's real current update left them. ---
        def _iso(dt: datetime | None) -> str | None:
            d = _to_date(dt)
            return d.isoformat() if d else None

        critical_count = 0
        activities_snapshot = []
        for act in parsed.activities:
            is_critical = _is_critical(act.total_float_hr_cnt, act.status_code, act.act_end_date)
            if is_critical:
                critical_count += 1
            status, pct = _derive_status(act.status_code, act.phys_complete_pct)
            activities_snapshot.append(
                {
                    "external_id": act.task_code,
                    "p6_task_id": act.task_id,
                    "name": act.task_name,
                    "wbs_path": act.wbs_id,
                    "task_type": act.task_type,
                    "planned_start": _iso(act.target_start_date),
                    "planned_finish": _iso(act.target_end_date),
                    "early_start": _iso(act.early_start_date),
                    "early_finish": _iso(act.early_end_date),
                    "actual_start": _iso(act.act_start_date),
                    "actual_finish": _iso(act.act_end_date),
                    "target_duration_hours": act.target_drtn_hr_cnt,
                    "remaining_duration_hours": act.remain_drtn_hr_cnt,
                    "constraint_type": act.cstr_type,
                    "constraint_date": _iso(act.cstr_date),
                    "is_critical": bool(is_critical),
                    "is_longest_path": bool(act.lp_critical),
                    "total_float_hours": act.total_float_hr_cnt,
                    "status": status.value,
                    "percent_complete": int(pct or 0),
                }
            )

        acts_by_task_id = {a.task_id: a for a in parsed.activities}
        relationships_snapshot = []
        for rel in parsed.relationships:
            link_type = _PRED_TYPE_TO_LINK_TYPE.get(rel.pred_type, LinkType.FS)
            pred_act = acts_by_task_id.get(rel.pred_task_id)
            succ_act = acts_by_task_id.get(rel.task_id)
            relationships_snapshot.append(
                {
                    "pred_external_id": pred_act.task_code if pred_act else rel.pred_task_id,
                    "pred_name": pred_act.task_name if pred_act else "",
                    "succ_external_id": succ_act.task_code if succ_act else rel.task_id,
                    "succ_name": succ_act.task_name if succ_act else "",
                    "link_type": link_type.value,
                    "lag_hours": rel.lag_hr_cnt,
                    "pred_critical": bool(
                        pred_act and _is_critical(pred_act.total_float_hr_cnt, pred_act.status_code, pred_act.act_end_date)
                    ),
                    "succ_critical": bool(
                        succ_act and _is_critical(succ_act.total_float_hr_cnt, succ_act.status_code, succ_act.act_end_date)
                    ),
                }
            )

    if reuse_import is not None:
        mark_current(db, ctx.tenant_id, project_id, import_id)
        db.commit()
        db.refresh(schedule_import)
        return schedule_import

    schedule_import.activity_count = len(parsed.activities)
    schedule_import.critical_count = critical_count
    schedule_import.warnings = parsed.parse_log
    schedule_import.relationships_snapshot = relationships_snapshot
    schedule_import.activities_snapshot = activities_snapshot
    schedule_import.wbs_snapshot = [
        {
            "wbs_id": node.wbs_id,
            "parent_wbs_id": node.parent_wbs_id,
            "wbs_short_name": node.wbs_short_name,
            "wbs_name": node.wbs_name,
            "seq_num": node.seq_num,
        }
        for node in parsed.wbs_nodes
    ]

    # Program Library: a project's very first .xer upload auto-locks as its
    # baseline (see services/baseline.py) — later uploads just keep
    # reconciling the live schedule as they already do above; the baseline
    # itself stays frozen, which is what makes EVM/S-curve variance
    # meaningful. Best-effort: a lockable-schedule edge case (BAC=0, no
    # planned dates) shouldn't fail an otherwise-successful import.
    # (is_first_import was already computed above, before the regression check.)
    if is_first_import:
        try:
            lock_baseline_for_project(db, ctx.tenant_id, project_id, import_id, ctx.user.id, version_label="Baseline")
        except BaselineLockError as e:
            schedule_import.warnings = [*schedule_import.warnings, f"Could not auto-lock baseline: {e}"]
    elif baseline_non_destructive:
        # Planning -> Baselines upload on a project that already has its own
        # current schedule: lock/overwrite the Performance Measurement
        # Baseline from THIS file's own parsed data (never the live tables),
        # so "Current update" and everything derived from it stay untouched.
        # Unlike the auto-lock above, locking the baseline IS the point of
        # this call, so a validation/conflict error is NOT swallowed into a
        # warning — it propagates to the caller (api/routes/evm.py), which
        # turns it into a proper 422/409 for the user.
        active_baseline = (
            db.query(Baseline)
            .filter(
                Baseline.tenant_id == ctx.tenant_id,
                Baseline.project_id == project_id,
                Baseline.status == BaselineStatus.active,
            )
            .first()
        )
        if active_baseline is not None:
            overwrite_active_baseline_from_parsed(db, ctx.tenant_id, project_id, parsed, import_id, ctx.user.id)
        else:
            lock_baseline_from_parsed(
                db, ctx.tenant_id, project_id, parsed, import_id, ctx.user.id,
                version_label=unique_baseline_label(db, project_id),
            )

    if not baseline_non_destructive:
        # A fresh live-schedule upload is always the new live schedule; a
        # baseline programme re-upload never re-points "Current update".
        mark_current(db, ctx.tenant_id, project_id, import_id)

    # Sync-log label. The baseline programme (first upload, or any upload via
    # Planning → Baselines) stays out of the UPD sequence and keeps its own
    # version label; ordinary status updates get the next per-project UPD-n.
    if revision_kind == "baseline" or is_first_import:
        schedule_import.revision_no = None
        schedule_import.revision_label = "Baseline programme"
    else:
        last_no = (
            db.query(func.max(ScheduleImport.revision_no))
            .filter(ScheduleImport.project_id == project_id, ScheduleImport.id != import_id)
            .scalar()
            or 0
        )
        schedule_import.revision_no = last_no + 1
        schedule_import.revision_label = f"UPD-{last_no + 1}"

    # Freeze this import's project-status rollup (SPI / DCMA quality / recovery
    # index / verdicts) so Execution → Project Status can trend status across
    # UPD-n — the live schedule tables keep no per-version history. Best-effort:
    # a rollup edge case must never fail an otherwise-good import, same policy
    # as the auto-baseline lock above. Skipped for a non-destructive baseline
    # upload: the live schedule didn't change, so there's nothing new to roll
    # up (recomputing it here would just duplicate the current rollup under
    # the wrong schedule_import_id).
    if not baseline_non_destructive:
        try:
            db.flush()
            rollup = compute_status_rollup(db, ctx.tenant_id, project_id)
            db.add(
                ScheduleStatusSnapshot(
                    id=uuid.uuid4(),
                    tenant_id=ctx.tenant_id,
                    project_id=project_id,
                    schedule_import_id=import_id,
                    data_date=schedule_import.data_date,
                    revision_label=schedule_import.revision_label,
                    spi=rollup.spi,
                    cpi=rollup.cpi,
                    schedule_recovery_index=rollup.schedule_recovery_index,
                    dcma_score=rollup.dcma_score,
                    dcma_status=rollup.dcma_status,
                    activity_count=rollup.activity_count,
                    critical_count=rollup.critical_count,
                    negative_float_count=rollup.negative_float_count,
                    overdue_count=rollup.overdue_count,
                    percent_complete=rollup.percent_complete,
                    progress_verdict=rollup.progress_verdict,
                    risk_verdict=rollup.risk_verdict,
                    quality_verdict=rollup.quality_verdict,
                )
            )
        except Exception as e:  # pragma: no cover - defensive
            schedule_import.warnings = [
                *schedule_import.warnings,
                f"Could not capture status snapshot: {e}",
            ]

    db.commit()
    db.refresh(schedule_import)
    return schedule_import
