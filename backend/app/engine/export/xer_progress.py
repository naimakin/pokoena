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

from app.models.activity import Activity, ActivityStatus
from app.parser.xer_parser import main_project_id

# P6 writes an ANSI file in the exporting client's locale, not UTF-8 (a real
# Turkish-locale export decodes as cp1254 and fails as utf-8). Round-trip
# whatever the source used so characters survive untouched.
_ENCODINGS = ("utf-8", "cp1254", "cp1252")

_STATUS_CODE = {
    ActivityStatus.not_started: "TK_NotStart",
    ActivityStatus.in_progress: "TK_Active",
    ActivityStatus.complete: "TK_Complete",
}

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


def _has_poko_progress(activity: Activity) -> bool:
    """Whether Poko holds an opinion about this activity's progress.

    Import only copies P6's actual dates onto a row the first time it sees it —
    after that they're subcontractor-owned and later imports leave them alone
    (see services/xer_import.py). So on an activity nobody has touched in Poko,
    our actuals are merely whatever the first import happened to carry, while
    P6's file has since moved on. Writing ours back would quietly undo real
    progress across the whole programme, so an untouched activity's row is
    passed through exactly as P6 wrote it.
    """
    return (
        (activity.percent_complete or 0) > 0
        or activity.actual_start is not None
        or activity.actual_finish is not None
        or activity.status != ActivityStatus.not_started
    )


def _remaining_hours(activity: Activity) -> float:
    if activity.status == ActivityStatus.complete:
        return 0.0
    if activity.remaining_duration_hours is not None:
        return activity.remaining_duration_hours
    return (activity.remaining_duration_days or 0) * 8.0


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
    # task_id, not task_code, so this must be known before it's rewritten.
    progressed: dict[str, Activity] = {}
    task_rows = 0
    for table, index, cells in _rows(lines):
        if table != "TASK":
            continue
        if main_proj and _cell(cells, index, "proj_id") not in ("", main_proj):
            continue
        task_rows += 1
        activity = by_code.get(_cell(cells, index, "task_code"))
        if activity is not None and _has_poko_progress(activity):
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
                    _patch_assignment_row(cells, index, activity)
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
    _put(cells, index, actual_col, f"{round(actual, 4):g}")
    _put(cells, index, remain_col, f"{round(max(0.0, budget - actual), 4):g}")


def _patch_assignment_row(cells: list[str], index: dict[str, int], activity: Activity) -> None:
    """One TASKRSRC row of a progressed activity: units follow the physical %,
    actual dates follow the activity's (see rewrite_progress)."""
    _split_units(cells, index, "target_qty", "act_reg_qty", "remain_qty", _fraction(activity))
    _put(
        cells, index, "act_start_date",
        _p6_datetime(activity.actual_start, _cell(cells, index, "act_start_date"), _DEFAULT_START_TIME),
    )
    _put(
        cells, index, "act_end_date",
        _p6_datetime(activity.actual_finish, _cell(cells, index, "act_end_date"), _DEFAULT_FINISH_TIME),
    )
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

    put("phys_complete_pct", str(int(activity.percent_complete or 0)))
    put("status_code", _STATUS_CODE.get(activity.status, "TK_NotStart"))
    put("act_start_date", _p6_datetime(activity.actual_start, current("act_start_date"), _DEFAULT_START_TIME))
    put("act_end_date", _p6_datetime(activity.actual_finish, current("act_end_date"), _DEFAULT_FINISH_TIME))
    put("remain_drtn_hr_cnt", f"{_remaining_hours(activity):g}")
    # Rolled-up units on the activity itself, same split as its assignments.
    fraction = _fraction(activity)
    _split_units(cells, index, "target_work_qty", "act_work_qty", "remain_work_qty", fraction)
    _split_units(cells, index, "target_equip_qty", "act_equip_qty", "remain_equip_qty", fraction)
    if activity.status == ActivityStatus.complete:
        # A finished activity has no float and no remaining dates. Left alone,
        # the file carried the float it had while still open, and P6 showed it
        # on a finished activity.
        put("total_float_hr_cnt", "0")
        put("free_float_hr_cnt", "0")
        put("restart_date", "")
        put("reend_date", "")
