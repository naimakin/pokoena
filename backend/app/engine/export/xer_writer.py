"""XER writer — serializes a project's current activities/relationships/
calendars/WBS back to a P6-compatible `.xer` file. Ported from the reference
project's `backend/app/engine/export/xer_writer.py` (294 lines), adapted to
read our SQLAlchemy DB rows directly instead of a `ProjectSnapshot`.

Intended workflow (per the reference's own docstring): a user edits progress
in Poko, downloads a `.xer`, runs P6's F9 recalculation on it, and re-uploads
the result via Project Files. So `task_id`/`proj_id` are written back using
P6's own original values (`Activity.p6_task_id`, `Project.p6_proj_id` —
captured at import time, see `services/xer_import.py`) rather than freshly
synthesized ones, so a re-import into the SAME P6 project is recognized as an
update to the activities that were exported, not new ones. Falls back to our
own UUIDs only for activities/projects that never went through an import
(created natively in Poko).

RSRC/TASKRSRC are now populated from real data (`Resource`/`ResourceAssignment`,
added for EVM — see `engine/evm/evm_engine.py`). ACTVTYPE/ACTVCODE/TASKACTV
stay empty — we still don't model activity codes. P6 (and our own parser)
tolerate a file where those tables are present but empty, same as the
reference.

Deliberate addition beyond the reference: a CALENDAR table. The reference's
writer omits it entirely (relying on the target P6 database already having
the calendar); we write it back from `Calendar.work_week`/`exceptions` so a
re-import — into our own system or a P6 database that doesn't already have
the calendar — doesn't silently fall back to the generic 5-day/8h default.
"""

from __future__ import annotations

import io
from datetime import date, datetime
from typing import Optional

from app.models.activity import Activity
from app.models.activity_relationship import ActivityRelationship, LinkType
from app.models.calendar import Calendar
from app.models.project import Project
from app.models.resource import Resource
from app.models.resource_assignment import ResourceAssignment
from app.models.wbs_node import WbsNode

_DATE_FMT = "%Y-%m-%d"  # our DB only stores dates, not times — parse_xer accepts this short form

_LINK_TYPE_TO_PRED_TYPE = {
    LinkType.FS: "PR_FS",
    LinkType.SS: "PR_SS",
    LinkType.FF: "PR_FF",
    LinkType.SF: "PR_SF",
}


def _d(d: Optional[date]) -> str:
    return d.strftime(_DATE_FMT) if d else ""


def _f(v: Optional[float], decimals: int = 2) -> str:
    return "" if v is None else f"{v:.{decimals}f}"


def _s(v: Optional[str]) -> str:
    return v or ""


def _tab(parts: list) -> str:
    return "\t".join(str(p) for p in parts)


def _hhmm(iso_time: str) -> str:
    """'08:00:00' or '08:00' -> '08:00' (see Calendar.work_week's stored shape)."""
    return iso_time[:5]


def _clndr_data(calendar: Calendar) -> str:
    """Inverse of xer_parser.py's `_parse_clndr_data` tokenizer."""
    tokens = []
    for day in sorted(calendar.work_week, key=lambda d: d["day_of_week"]):
        parts = [str(day["day_of_week"])]
        for shift in day["shifts"]:
            parts.append(_hhmm(shift["start"]))
            parts.append(_hhmm(shift["end"]))
        tokens.append("(" + "|".join(parts) + ")")
    for exc in calendar.exceptions:
        exc_date = exc["exc_date"][:10]  # ISO date prefix, e.g. "2026-01-01" from "2026-01-01T00:00:00"
        parts = [exc_date]
        for shift in exc["shifts"]:
            parts.append(_hhmm(shift["start"]))
            parts.append(_hhmm(shift["end"]))
        tokens.append("(" + "|".join(parts) + ")")
    return "".join(tokens)


def _write_ermhdr(buf: io.StringIO) -> None:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    buf.write(f"ERMHDR\t19.12\t{now}\tPoko\tP6 Professional\tUnicode\t19.12\n")


def _write_project(buf: io.StringIO, project: Project, default_clndr_id: str, data_date: Optional[datetime]) -> None:
    buf.write("%T\tPROJECT\n")
    buf.write("%F\tproj_id\tproj_short_name\tproj_name\tlast_recalc_date\tlast_fin_date\tplan_start_date\tclndr_id\n")
    buf.write(
        "%R\t"
        + _tab(
            [
                _s(project.p6_proj_id or project.code),
                _s(project.p6_proj_short_name or project.code),
                _s(project.name),
                data_date.strftime("%Y-%m-%d %H:%M") if data_date else "",
                "",
                data_date.strftime("%Y-%m-%d %H:%M") if data_date else "",
                _s(default_clndr_id),
            ]
        )
        + "\n"
    )


def _write_calendars(buf: io.StringIO, calendars: list[Calendar]) -> None:
    buf.write("%T\tCALENDAR\n")
    buf.write("%F\tclndr_id\tclndr_name\tproj_id\tclndr_data\n")
    for cal in calendars:
        buf.write("%R\t" + _tab([_s(cal.clndr_id), _s(cal.name), "", _clndr_data(cal)]) + "\n")


def _write_projwbs(buf: io.StringIO, nodes: list[WbsNode], proj_id: str) -> None:
    buf.write("%T\tPROJWBS\n")
    buf.write("%F\twbs_id\tproj_id\tparent_wbs_id\twbs_short_name\twbs_name\tseq_num\n")
    for n in nodes:
        buf.write(
            "%R\t"
            + _tab(
                [
                    _s(n.wbs_id),
                    proj_id,
                    _s(n.parent_wbs_id),
                    _s(n.wbs_short_name),
                    _s(n.wbs_name),
                    "" if n.seq_num is None else str(n.seq_num),
                ]
            )
            + "\n"
        )


def _write_task(buf: io.StringIO, activities: list[Activity], proj_id: str, clndr_id_by_row_id: dict) -> None:
    buf.write("%T\tTASK\n")
    cols = [
        "task_id", "proj_id", "wbs_id", "clndr_id",
        "task_code", "task_name", "task_type", "status_code",
        "phys_complete_pct",
        "target_drtn_hr_cnt", "remain_drtn_hr_cnt",
        "early_start_date", "early_end_date",
        "late_start_date", "late_end_date",
        "act_start_date", "act_end_date",
        "target_start_date", "target_end_date",
        "restart_date", "reend_date",
        "total_float_hr_cnt", "free_float_hr_cnt",
        "cstr_type", "cstr_date",
        "cstr_type2", "cstr_date2",
        "seq_num",
    ]
    buf.write("%F\t" + "\t".join(cols) + "\n")

    for a in activities:
        buf.write(
            "%R\t"
            + _tab(
                [
                    _s(a.p6_task_id or str(a.id)),
                    proj_id,
                    _s(a.wbs_path),
                    _s(clndr_id_by_row_id.get(a.clndr_id, "")),
                    _s(a.external_id),
                    _s(a.name),
                    _s(a.task_type) or "TT_Task",
                    _s(a.status_code) or "TK_NotStart",
                    _f(float(a.percent_complete)),
                    _f(a.target_duration_hours),
                    _f(a.remaining_duration_hours),
                    _d(a.early_start),
                    _d(a.early_finish),
                    _d(a.late_start),
                    _d(a.late_finish),
                    _d(a.actual_start),
                    _d(a.actual_finish),
                    _d(a.planned_start),
                    _d(a.planned_finish),
                    "",  # restart_date — not modeled
                    "",  # reend_date — not modeled
                    _f(a.total_float_hours),
                    _f(a.free_float_hours),
                    _s(a.constraint_type),
                    _d(a.constraint_date),
                    _s(a.constraint_type_2),
                    _d(a.constraint_date_2),
                    "",  # seq_num — not modeled
                ]
            )
            + "\n"
        )


def _write_taskpred(buf: io.StringIO, relationships: list[ActivityRelationship], task_id_by_row_id: dict) -> None:
    buf.write("%T\tTASKPRED\n")
    buf.write("%F\ttask_pred_id\ttask_id\tpred_task_id\tpred_type\tlag_hr_cnt\n")
    for i, r in enumerate(relationships, start=1):
        buf.write(
            "%R\t"
            + _tab(
                [
                    str(i),
                    task_id_by_row_id.get(r.successor_id, ""),
                    task_id_by_row_id.get(r.predecessor_id, ""),
                    _LINK_TYPE_TO_PRED_TYPE.get(r.link_type, "PR_FS"),
                    _f(float(r.lag_hours or 0)),
                ]
            )
            + "\n"
        )


def _write_rsrc(buf: io.StringIO, resources: list[Resource]) -> None:
    buf.write("%T\tRSRC\n")
    buf.write("%F\trsrc_id\trsrc_name\trsrc_short_name\trsrc_type\tunit_id\tclndr_id\tcurr_id\n")
    for r in resources:
        buf.write(
            "%R\t" + _tab([_s(r.rsrc_id), _s(r.name), _s(r.short_name), _s(r.rsrc_type), _s(r.unit_id), _s(r.clndr_id), _s(r.curr_id)])
            + "\n"
        )


def _write_taskrsrc(
    buf: io.StringIO, assignments: list[ResourceAssignment], task_id_by_row_id: dict, rsrc_id_by_row_id: dict
) -> None:
    buf.write("%T\tTASKRSRC\n")
    buf.write(
        "%F\ttaskrsrc_id\ttask_id\trsrc_id\tremain_qty\ttarget_qty\tact_reg_qty\t"
        "target_cost\tact_reg_cost\tremain_cost\tunit_id\n"
    )
    for i, a in enumerate(assignments, start=1):
        buf.write(
            "%R\t"
            + _tab(
                [
                    str(i),
                    task_id_by_row_id.get(a.activity_id, ""),
                    rsrc_id_by_row_id.get(a.resource_id, ""),
                    _f(a.remain_qty),
                    _f(a.target_qty),
                    _f(a.act_reg_qty),
                    _f(a.target_cost),
                    _f(a.act_reg_cost),
                    _f(a.remain_cost),
                    _s(a.unit_id),
                ]
            )
            + "\n"
        )


def _write_empty_table(buf: io.StringIO, name: str, columns: list[str]) -> None:
    buf.write(f"%T\t{name}\n")
    buf.write("%F\t" + "\t".join(columns) + "\n")


def build_xer(
    project: Project,
    activities: list[Activity],
    relationships: list[ActivityRelationship],
    calendars: list[Calendar],
    wbs_nodes: list[WbsNode],
    resources: list[Resource],
    assignments: list[ResourceAssignment],
    data_date: Optional[datetime],
) -> bytes:
    """Serialize a project's current schedule back to XER format. Returns
    UTF-8 bytes ready for a file-download response."""
    buf = io.StringIO()

    proj_id = project.p6_proj_id or project.code
    default_clndr_id = calendars[0].clndr_id if calendars else ""
    clndr_id_by_row_id = {c.id: c.clndr_id for c in calendars}
    task_id_by_row_id = {a.id: (a.p6_task_id or str(a.id)) for a in activities}
    rsrc_id_by_row_id = {r.id: r.rsrc_id for r in resources}

    _write_ermhdr(buf)
    _write_project(buf, project, default_clndr_id, data_date)
    _write_calendars(buf, calendars)
    _write_projwbs(buf, wbs_nodes, proj_id)
    _write_task(buf, activities, proj_id, clndr_id_by_row_id)
    _write_taskpred(buf, relationships, task_id_by_row_id)
    _write_rsrc(buf, resources)
    _write_taskrsrc(buf, assignments, task_id_by_row_id, rsrc_id_by_row_id)
    _write_empty_table(buf, "ACTVTYPE", ["actv_code_type_id", "actv_code_type", "proj_id"])
    _write_empty_table(
        buf, "ACTVCODE", ["actv_code_id", "actv_code_type_id", "actv_code_name", "short_name", "parent_actv_code_id", "seq_num"]
    )
    _write_empty_table(buf, "TASKACTV", ["task_id", "actv_code_type_id", "actv_code_id"])

    buf.write("%E\n")

    return buf.getvalue().encode("utf-8")
