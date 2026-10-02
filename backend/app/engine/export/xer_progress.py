"""Write Poko's progress back into the project's ORIGINAL P6 .xer.

Why patch instead of generate: a real P6 export carries ~12 tables, and the ones
that matter are far wider than anything we model — PROJECT has 71 columns,
TASK 61, PROJWBS 26 (including `proj_node_flag`, which is what tells P6 which
WBS row is the project node). It also carries GUIDs, OBS, SCHEDOPTIONS, UDF
definitions and a `clndr_data` blob in a nested format of its own. P6's importer
rejects, or silently imports as empty, a file that doesn't carry all of that —
which is exactly what happened to `xer_writer.build_xer`'s output: our own
parser is lenient enough to read it back, so the round-trip looked fine in
tests, while P6 opened it as an empty project.

So the export starts from the file P6 itself produced (kept on
`ScheduleImport.source_file`) and rewrites only the handful of TASK columns a
user can change in Poko. Everything else passes through byte-for-byte, so P6
accepts the file on the same terms it accepted its own export, and the user's
progress lands on the right activities.

`xer_writer.build_xer` stays as the fallback for a project whose import predates
source-file capture — see routes/export.py.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

from app.engine.durations import activity_hours_per_day
from app.models.activity import FINISH_MILESTONE, MILESTONE_TYPES, P6_STATUS_CODE, Activity, ActivityStatus
from app.models.resource import LABOR
from app.parser.xer_parser import main_project_id

# P6 writes an ANSI file in the exporting client's locale, not UTF-8 (a real
# Turkish-locale export decodes as cp1254 and fails as utf-8). Round-trip
# whatever the source used so characters survive untouched.
_ENCODINGS = ("utf-8", "cp1254", "cp1252")

# P6 stores a datetime; our columns are dates. Keep the time the source row
# already had for that field, and otherwise use P6's own working-day convention.
_DEFAULT_START_TIME = "08:00"
_DEFAULT_FINISH_TIME = "17:00"


def decode_xer(raw: bytes) -> tuple[str, str]:
    """Returns (text, encoding). Tries the encodings P6 actually emits."""
    for encoding in _ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("cp1252", errors="replace"), "cp1252"


def _p6_datetime(value: Optional[date], existing: str, default_time: str) -> str:
    if value is None:
        return ""
    time_part = existing[11:16] if len(existing) >= 16 else ""
    return f"{value.isoformat()} {time_part or default_time}"


def _num(value: float) -> str:
    """A quantity the way P6 writes one: plain decimal, no exponent, no
    trailing zeros, up to 6 places. (`:g` keeps only 6 SIGNIFICANT digits, so
    22255.74 x 40% went out as 8902.3 / 13353.4 and the units no longer added
    up to the budget.)"""
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _phys(activity: Activity) -> float:
    phys = getattr(activity, "phys_complete_pct", None)
    return float(activity.percent_complete or 0) if phys is None else float(phys)


def _differs_from_row(cells: list[str], index: dict[str, int], activity: Activity) -> bool:
    """Whether Poko's progress on this activity differs from what the file's
    TASK row says. Only those rows are rewritten; every other row passes
    through byte-for-byte as P6 wrote it. Comparing with the row (rather than
    "has Poko any progress") is what lets an UNDO reach P6 — an activity put
    back to Not Started has no progress of its own, but its row still says
    Complete — and keeps untouched finished work from being re-serialized."""

    def date_cell(column: str) -> str:
        return _cell(cells, index, column)[:10]

    def iso(value: Optional[date]) -> str:
        return value.isoformat() if value else ""

    if _cell(cells, index, "status_code") != P6_STATUS_CODE.get(activity.status, "TK_NotStart"):
        return True
    if date_cell("act_start_date") != iso(activity.actual_start):
        return True
    if date_cell("act_end_date") != iso(activity.actual_finish):
        return True
    try:
        if abs(float(_cell(cells, index, "phys_complete_pct") or 0) - _phys(activity)) > 0.5:
            return True
        if (
            getattr(activity, "remaining_duration_hours", None) is not None
            and abs(float(_cell(cells, index, "remain_drtn_hr_cnt") or 0) - _remaining_hours(activity)) > 0.01
        ):
            return True
    except ValueError:
        return True
    return False


def _remaining_hours(activity: Activity) -> float:
    if activity.status == ActivityStatus.complete:
        return 0.0
    if activity.remaining_duration_hours is not None:
        return activity.remaining_duration_hours
    # Days back to hours on the activity's own calendar (engine/durations.py).
    return (activity.remaining_duration_days or 0) * activity_hours_per_day(activity)


def rewrite_progress(source: bytes, activities: Iterable[Activity]) -> tuple[bytes, int, int]:
    """Patch `source` (a P6 .xer) with Poko's progress.

    Returns (bytes, activities in the file, rows Poko's progress was written
    into). Activities are matched on task_code == Activity.external_id, the same
    key the importer upserts on, within the file's main project only.

    Two tables are written: TASK (status, %, actual dates, remaining duration,
    float, rolled-up units) and TASKRSRC for the same activities (actual and
    remaining units, actual dates). The second matters as much as the first: an
    assignment that drives its activity's dates (P6's default) makes P6
    re-derive the activity's actual start/finish from the ASSIGNMENT on import,
    so a file whose TASK row said one finish date while its assignment still
    said another opened in P6 with the assignment's date.
    """
    text, encoding = decode_xer(source)
    lines = text.split("\n")
    by_code = {a.external_id: a for a in activities}
    main_proj = _main_proj_id(lines)

    # Pass 1: which P6 task_ids get Poko's progress. TASKRSRC references
    # task_id, not task_code, so this must be known before it's rewritten —
    # as must which resources are labor (RSRC), the only ones whose units
    # follow the % (services/activity_progress.py).
    progressed: dict[str, Activity] = {}
    labor_rsrc_ids: set[str] = set()
    task_rows = 0
    for table, index, cells in _rows(lines):
        if table == "RSRC" and _cell(cells, index, "rsrc_type") == LABOR:
            labor_rsrc_ids.add(_cell(cells, index, "rsrc_id"))
        if table != "TASK":
            continue
        if main_proj and _cell(cells, index, "proj_id") not in ("", main_proj):
            continue
        task_rows += 1
        activity = by_code.get(_cell(cells, index, "task_code"))
        if activity is not None and _differs_from_row(cells, index, activity):
            progressed[_cell(cells, index, "task_id")] = activity

    # Pass 2: rewrite. Every other byte passes through as P6 wrote it.
    out: list[str] = []
    table: str | None = None
    index: dict[str, int] = {}
    for raw_line in lines:
        # P6 writes CRLF. Keep each line's own terminator so the only bytes that
        # differ from the source are the progress cells themselves.
        crlf = raw_line.endswith("\r")
        line = raw_line[:-1] if crlf else raw_line
        patched = line

        if line.startswith("%T\t"):
            table = line.split("\t")[1]
            index = {}
        elif line.startswith("%F\t"):
            index = {name: i for i, name in enumerate(line.split("\t")[1:])}
        elif line.startswith("%R\t") and table in ("TASK", "TASKRSRC") and index:
            cells = line.split("\t")[1:]
            activity = progressed.get(_cell(cells, index, "task_id"))
            if activity is not None:
                if table == "TASK":
                    _patch_task_row(cells, index, activity)
                else:
                    is_labor = (
                        _cell(cells, index, "rsrc_type") == LABOR
                        or _cell(cells, index, "rsrc_id") in labor_rsrc_ids
                    )
                    _patch_assignment_row(cells, index, activity, is_labor)
                patched = "%R\t" + "\t".join(cells)

        out.append(patched + "\r" if crlf else patched)

    return "\n".join(out).encode(encoding, errors="replace"), task_rows, len(progressed)


def _rows(lines: list[str]):
    """(table, column index, cells) for every %R line."""
    table: str | None = None
    index: dict[str, int] = {}
    for raw in lines:
        line = raw.rstrip("\r")
        if line.startswith("%T\t"):
            table = line.split("\t")[1]
            index = {}
        elif line.startswith("%F\t"):
            index = {name: i for i, name in enumerate(line.split("\t")[1:])}
        elif line.startswith("%R\t") and index:
            yield table, index, line.split("\t")[1:]


def _main_proj_id(lines: list[str]) -> str:
    """proj_id of the project the file is about. Baselines exported alongside
    it carry the same task_codes and must pass through untouched — same rule as
    the importer (parser/xer_parser.py::main_project_id)."""
    project_rows: list[dict[str, str]] = []
    for table, index, cells in _rows(lines):
        if table == "PROJECT":
            project_rows.append({name: _cell(cells, index, name) for name in index})
        elif project_rows:
            break
    return main_project_id(project_rows)


def _cell(cells: list[str], index: dict[str, int], column: str) -> str:
    at = index.get(column)
    return cells[at] if at is not None and at < len(cells) else ""


def _put(cells: list[str], index: dict[str, int], column: str, value: str) -> None:
    at = index.get(column)
    if at is not None and at < len(cells):
        cells[at] = value


def _fraction(activity: Activity) -> float:
    if activity.status == ActivityStatus.complete:
        return 1.0
    return max(0.0, min(100.0, float(activity.percent_complete or 0))) / 100.0


def _split_units(
    cells: list[str], index: dict[str, int], budget_col: str, actual_col: str, remain_col: str, fraction: float
) -> None:
    """actual = budget x %, remaining = budget - actual — only where the file
    has the columns to hold it."""
    if budget_col not in index or actual_col not in index:
        return
    try:
        budget = float(_cell(cells, index, budget_col) or 0)
    except ValueError:
        return
    actual = budget * fraction
    actual = round(actual, 6)
    _put(cells, index, actual_col, _num(actual))
    _put(cells, index, remain_col, _num(max(0.0, round(budget - actual, 6))))


def _actual_dates(activity: Activity, existing_start: str, existing_end: str) -> tuple[str, str]:
    """(act_start_date, act_end_date) cells for the activity. A milestone has
    one moment, and P6 writes it into BOTH columns, identically — a finish
    milestone's at its finish time, a start milestone's at its start time —
    so whichever of the two Poko holds is written to both."""
    task_type = getattr(activity, "task_type", None)
    if task_type in MILESTONE_TYPES and (activity.actual_start or activity.actual_finish):
        if task_type == FINISH_MILESTONE:
            moment = _p6_datetime(
                activity.actual_finish or activity.actual_start, existing_end or existing_start, _DEFAULT_FINISH_TIME
            )
        else:
            moment = _p6_datetime(
                activity.actual_start or activity.actual_finish, existing_start or existing_end, _DEFAULT_START_TIME
            )
        return moment, moment
    return (
        _p6_datetime(activity.actual_start, existing_start, _DEFAULT_START_TIME),
        _p6_datetime(activity.actual_finish, existing_end, _DEFAULT_FINISH_TIME),
    )


def _patch_assignment_row(cells: list[str], index: dict[str, int], activity: Activity, is_labor: bool) -> None:
    """One TASKRSRC row of a progressed activity: a labor assignment's units
    follow the activity's %, every assignment's actual dates follow the
    activity's (see rewrite_progress)."""
    if is_labor:
        _split_units(cells, index, "target_qty", "act_reg_qty", "remain_qty", _fraction(activity))
    start, end = _actual_dates(activity, _cell(cells, index, "act_start_date"), _cell(cells, index, "act_end_date"))
    _put(cells, index, "act_start_date", start)
    _put(cells, index, "act_end_date", end)
    if activity.status == ActivityStatus.complete:
        # Nothing remains, so no remaining dates — as P6 writes a finished assignment.
        _put(cells, index, "restart_date", "")
        _put(cells, index, "reend_date", "")


def _patch_task_row(cells: list[str], index: dict[str, int], activity: Activity) -> None:
    """Overwrite the progress columns in one TASK row, in place."""

    def put(column: str, value: str) -> None:
        _put(cells, index, column, value)

    def current(column: str) -> str:
        return _cell(cells, index, column)

    put("phys_complete_pct", _num(round(_phys(activity), 2)))
    put("status_code", P6_STATUS_CODE.get(activity.status, "TK_NotStart"))
    start, end = _actual_dates(activity, current("act_start_date"), current("act_end_date"))
    put("act_start_date", start)
    put("act_end_date", end)
    put("remain_drtn_hr_cnt", _num(_remaining_hours(activity)))
    # Rolled-up labor units on the activity itself (TASK.act_work_qty = the sum
    # of its labor assignments' act_reg_qty), same split as those assignments.
    # Nonlabor units (act_equip_qty) don't follow the % — see TASKRSRC above.
    _split_units(cells, index, "target_work_qty", "act_work_qty", "remain_work_qty", _fraction(activity))
    if activity.status == ActivityStatus.complete:
        # A finished activity has no float and no remaining dates — P6 writes
        # both floats BLANK on finished work (not 0). Left alone, the file
        # carried the float it had while still open, and P6 showed it on a
        # finished activity.
        put("total_float_hr_cnt", "")
        put("free_float_hr_cnt", "")
        put("restart_date", "")
        put("reend_date", "")
