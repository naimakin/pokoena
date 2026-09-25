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
    key the importer upserts on.
    """
    text, encoding = decode_xer(source)
    by_code = {a.external_id: a for a in activities}

    out: list[str] = []
    table: str | None = None
    index: dict[str, int] = {}
    task_rows = 0
    updated = 0

    for raw_line in text.split("\n"):
        # P6 writes CRLF. Keep each line's own terminator so the only bytes that
        # differ from the source are the progress cells themselves.
        crlf = raw_line.endswith("\r")
        line = raw_line[:-1] if crlf else raw_line
        patched = line

        if line.startswith("%T\t"):
            table = line.split("\t")[1]
            index = {}
        elif line.startswith("%F\t") and table == "TASK":
            index = {name: i for i, name in enumerate(line.split("\t")[1:])}
        elif line.startswith("%R\t") and table == "TASK" and index:
            task_rows += 1
            cells = line.split("\t")[1:]
            code_at = index.get("task_code")
            activity = by_code.get(cells[code_at]) if code_at is not None and code_at < len(cells) else None
            if activity is not None and _has_poko_progress(activity):
                _patch_task_row(cells, index, activity)
                updated += 1
                patched = "%R\t" + "\t".join(cells)

        out.append(patched + "\r" if crlf else patched)

    return "\n".join(out).encode(encoding, errors="replace"), task_rows, updated


def _patch_task_row(cells: list[str], index: dict[str, int], activity: Activity) -> None:
    """Overwrite the progress columns in one TASK row, in place."""

    def put(column: str, value: str) -> None:
        at = index.get(column)
        if at is not None and at < len(cells):
            cells[at] = value

    def current(column: str) -> str:
        at = index.get(column)
        return cells[at] if at is not None and at < len(cells) else ""

    put("phys_complete_pct", str(int(activity.percent_complete or 0)))
    put("status_code", _STATUS_CODE.get(activity.status, "TK_NotStart"))
    put("act_start_date", _p6_datetime(activity.actual_start, current("act_start_date"), _DEFAULT_START_TIME))
    put("act_end_date", _p6_datetime(activity.actual_finish, current("act_end_date"), _DEFAULT_FINISH_TIME))
    put("remain_drtn_hr_cnt", f"{_remaining_hours(activity):g}")
