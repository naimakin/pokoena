"""Parses a Primavera P6 `.xer` file into the canonical dataclasses in
`xer_models.py`. Ported from a colleague's reference P6 desktop app
(`backend/app/parser/xer_parser.py` there), with two changes:

1. Takes raw `bytes` rather than a filesystem `Path` — this service has no local
   disk to read from (and shouldn't; see `services/xer_import.py` for where the
   result actually lands: Postgres, not a JSON file).
2. Trimmed to what CPM scheduling + EVM + activity codes need: WBS, calendars,
   activities, relationships, resource assignments (RSRC/TASKRSRC), and
   activity codes (ACTVTYPE/ACTVCODE/TASKACTV). Everything the reference
   parser reads is now ported.

Encoding strategy: try UTF-8 first, fall back to latin-1 (Windows-1252), same as
the reference. Everything else — the multi-version `clndr_data` tokenizer, the
two-layer (global vs. project-specific) calendar priority, the audit-trail
`parse_log` — is unchanged.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, time, timedelta
from typing import Optional

from app.parser.xer_models import (
    Activity,
    ActivityCode,
    Calendar,
    CalendarDay,
    CalendarException,
    CodeType,
    CodeValue,
    DayShift,
    ParsedSchedule,
    ProjectMeta,
    Relationship,
    Resource,
    ResourceAssignment,
    WbsNode,
)

logger = logging.getLogger(__name__)

_P6_DATE_FMT = "%Y-%m-%d %H:%M"
_P6_DATE_FMT_SHORT = "%Y-%m-%d"

MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB hard limit


class XerParseError(ValueError):
    """File too large, no PROJECT table, or otherwise unparseable."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_date(value: str) -> Optional[datetime]:
    if not value or value.strip() == "":
        return None
    v = value.strip()
    for fmt in (_P6_DATE_FMT, _P6_DATE_FMT_SHORT):
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    logger.warning("Cannot parse date: %r", value)
    return None


def _safe_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value) if value and value.strip() != "" else default
    except (ValueError, TypeError):
        return default


def _safe_int(value: str, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(value) if value and value.strip() != "" else default
    except (ValueError, TypeError):
        return default


def _decode(file_bytes: bytes) -> str:
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        logger.warning("UTF-8 decode failed for XER upload — retrying with latin-1")
        return file_bytes.decode("latin-1")


# ---------------------------------------------------------------------------
# Raw XER table reader
# ---------------------------------------------------------------------------


def _read_tables(text: str, parse_log: list[str]) -> dict[str, list[dict[str, str]]]:
    """Read all %T/%F/%R blocks. Returns { table_name: [ {col: value, ...} ] }."""
    tables: dict[str, list[dict[str, str]]] = {}
    current_table: Optional[str] = None
    current_cols: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r\n")
        if not line:
            continue

        if line.startswith("%T"):
            current_table = line[2:].strip()
            current_cols = []
            tables[current_table] = []
        elif line.startswith("%F"):
            current_cols = line[2:].strip().split("\t")
        elif line.startswith("%R"):
            if current_table is None or not current_cols:
                continue
            values = line[2:].strip().split("\t")
            while len(values) < len(current_cols):
                values.append("")
            row = dict(zip(current_cols, values[: len(current_cols)]))
            tables[current_table].append(row)

    for tname, rows in tables.items():
        parse_log.append(f"TABLE {tname}: {len(rows)} rows")

    return tables


# ---------------------------------------------------------------------------
# clndr_data parser — multi-version P6 support
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"\(([^)]*)\)")
_TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")

_DATE_VARIANTS = ["%Y-%m-%d", "%m/%d/%Y", "%d-%b-%Y", "%d-%B-%Y"]


def _try_parse_exc_date(key: str) -> Optional[datetime]:
    key = key.strip()
    for fmt in _DATE_VARIANTS:
        try:
            return datetime.strptime(key, fmt)
        except ValueError:
            continue
    return None


def _parse_shifts_from_token(token: str) -> list[DayShift]:
    """Extract HH:MM pairs from a token string (start, end). Odd trailing time
    is ignored; unknown format logs a warning and yields no shifts (non-working)."""
    times = _TIME_RE.findall(token)
    shifts: list[DayShift] = []
    for i in range(0, len(times) - 1, 2):
        try:
            start = time(int(times[i][0]), int(times[i][1]))
            end = time(int(times[i + 1][0]), int(times[i + 1][1]))
            shifts.append(DayShift(start=start, end=end))
        except ValueError as e:
            logger.warning("clndr_data: invalid time in token %r — %s", token, e)
    return shifts


def _parse_clndr_data_legacy(
    clndr_id: str, clndr_data: str, parse_log: list[str]
) -> tuple[list[CalendarDay], list[CalendarException]]:
    """Parse the older, flat `(dow|HH:MM|HH:MM)...` clndr_data variant — what
    this project's own synthetic test fixture uses. Unknown tokens produce a
    warning + parse_log entry rather than a silent error.

    Token key: 0-6 → weekday (0=Sun ... 6=Sat); a date string → exception; anything
    else → warning + skip.
    """
    week: dict[int, CalendarDay] = {}
    exceptions: list[CalendarException] = []
    unknown_count = 0

    for m in _TOKEN_RE.finditer(clndr_data):
        token = m.group(1)
        if not token.strip():
            continue

        parts = token.split("|")
        key = parts[0].strip()

        if key.isdigit():
            dow = int(key)
            if 0 <= dow <= 6:
                shifts = _parse_shifts_from_token(token)
                week[dow] = CalendarDay(day_of_week=dow, shifts=shifts)
                continue

        exc_date = _try_parse_exc_date(key)
        if exc_date:
            shifts = _parse_shifts_from_token(token)
            exceptions.append(CalendarException(exc_date=exc_date, shifts=shifts))
            continue

        unknown_count += 1
        msg = f"CAL {clndr_id}: unrecognised clndr_data token {token!r} — skipped"
        logger.warning(msg)
        parse_log.append(f"WARNING: {msg}")

    if unknown_count:
        parse_log.append(f"CAL {clndr_id}: {unknown_count} unknown token(s) skipped in clndr_data")

    week_list = [week.get(dow, CalendarDay(day_of_week=dow, shifts=[])) for dow in range(7)]
    return week_list, exceptions


# ---------------------------------------------------------------------------
# clndr_data parser — modern nested variant (real-world P6 exports)
# ---------------------------------------------------------------------------
#
# Every real .xer this app has been handed so far uses this format, not the
# flat one above — a genuine S-expression tree, not a flat token list:
#
#   (0||CalendarData()(
#     (0||DaysOfWeek()(
#       (0||1()(                          <- day 1 (P6: 1=Sun ... 7=Sat)
#         (0||0(s|07:00|f|12:00)())       <- shift 0: 07:00-12:00
#         (0||1(s|13:00|f|18:00)())))     <- shift 1: 13:00-18:00
#       ...
#       (0||6()())))                     <- day 6, no shifts (day off)
#     (0||VIEW(ShowTotal|N)())
#     (0||Exceptions()(
#       (0||41(d|42536)(                 <- exception, day-serial 42536
#         (0||0(s|00:00|f|00:30)()) ...))))))
#
# Every node is `(0||KEY(PAYLOAD)(CHILD*))` — KEY is always prefixed "0||",
# PAYLOAD is flat pipe-delimited data (never nested), CHILD* is zero or more
# sibling nodes of the same shape. Genuinely recursive, so it needs a real
# parser, not a single-level regex (which is what silently produced empty
# calendars — and a scheduler that could never find a working day — the
# first time a real, non-synthetic .xer went through this app).

# Exception dates are stored as a day count from P6's serial-date epoch —
# the same 1899-12-30 base OLE Automation / Delphi TDateTime uses (P6's
# desktop client is Delphi-based), confirmed against a real calendar's
# exceptions landing on plausible holiday dates once converted.
_P6_SERIAL_DATE_EPOCH = datetime(1899, 12, 30)


class _NestedNode:
    __slots__ = ("key", "payload", "children")

    def __init__(self, key: str, payload: str, children: list["_NestedNode"]):
        self.key = key
        self.payload = payload
        self.children = children


def _parse_nested_node(s: str, i: int) -> tuple[_NestedNode, int]:
    """Parse one `(0||KEY(PAYLOAD)(CHILD*))` node starting at s[i] == '('.
    Returns (node, index just past the node's closing ')')."""
    header_end = s.index("(", i + 1)
    header = s[i + 1 : header_end]
    key = header.split("||", 1)[1] if "||" in header else header

    payload_end = s.index(")", header_end)
    payload = s[header_end + 1 : payload_end]

    children_start = payload_end + 1  # points at the children group's '('
    depth = 1
    j = children_start + 1
    while depth > 0:
        if s[j] == "(":
            depth += 1
        elif s[j] == ")":
            depth -= 1
        j += 1
    children_end = j - 1  # index of the children group's matching ')'

    children: list[_NestedNode] = []
    k = children_start + 1
    while k < children_end:
        if s[k] != "(":
            k += 1
            continue
        child, k = _parse_nested_node(s, k)
        children.append(child)

    node_end = children_end + 1  # the node's own closing ')'
    return _NestedNode(key=key, payload=payload, children=children), node_end + 1


def _parse_nested_shift(node: _NestedNode) -> Optional[DayShift]:
    parts = node.payload.split("|")
    if len(parts) < 4:
        return None
    try:
        sh, sm = (int(x) for x in parts[1].split(":"))
        eh, em = (int(x) for x in parts[3].split(":"))
        return DayShift(start=time(sh, sm), end=time(eh, em))
    except (ValueError, IndexError):
        return None


def _parse_clndr_data_nested(
    clndr_id: str, clndr_data: str, parse_log: list[str]
) -> tuple[list[CalendarDay], list[CalendarException]]:
    week: dict[int, CalendarDay] = {}
    exceptions: list[CalendarException] = []

    try:
        root, _ = _parse_nested_node(clndr_data, clndr_data.index("("))
    except (ValueError, IndexError) as e:
        msg = f"CAL {clndr_id}: failed to parse nested clndr_data — {e}"
        logger.warning(msg)
        parse_log.append(f"WARNING: {msg}")
        return [], []

    for section in root.children:
        if section.key == "DaysOfWeek":
            for day_node in section.children:
                try:
                    p6_day_num = int(day_node.key)  # 1=Sun ... 7=Sat
                except ValueError:
                    continue
                dow = p6_day_num - 1  # -> this app's 0=Sun ... 6=Sat convention
                if not (0 <= dow <= 6):
                    continue
                shifts = [s for s in (_parse_nested_shift(c) for c in day_node.children) if s]
                week[dow] = CalendarDay(day_of_week=dow, shifts=shifts)
        elif section.key == "Exceptions":
            for exc_node in section.children:
                parts = exc_node.payload.split("|")
                if len(parts) < 2 or parts[0] != "d":
                    continue
                try:
                    serial = int(parts[1])
                except ValueError:
                    continue
                exc_date = _P6_SERIAL_DATE_EPOCH + timedelta(days=serial)
                shifts = [s for s in (_parse_nested_shift(c) for c in exc_node.children) if s]
                exceptions.append(CalendarException(exc_date=exc_date, shifts=shifts))
        # VIEW and anything else are P6 UI display state, not schedule data.

    week_list = [week.get(dow, CalendarDay(day_of_week=dow, shifts=[])) for dow in range(7)]
    return week_list, exceptions


_NESTED_MARKER = "(0||"
# How many leading characters of noise (non-printable bytes some real
# exports have been seen prefixing this field with — e.g. a couple of stray
# \x7f/DEL bytes) to tolerate before giving up on "this is the nested
# format". str.strip() only removes whitespace, not control characters, so
# a plain startswith() check is not enough on its own.
_NESTED_MARKER_SEARCH_WINDOW = 20


def _parse_clndr_data(
    clndr_id: str, clndr_data: str, parse_log: list[str]
) -> tuple[list[CalendarDay], list[CalendarException]]:
    """Dispatches to whichever clndr_data variant this calendar actually uses.
    The nested format always contains a `(0||` node header near the very
    start — real exports have shown up with a couple of stray non-printable
    bytes ahead of it, so this looks for the marker within a small leading
    window instead of anchoring strictly to index 0 (which silently fell
    back to the legacy parser, garbling every real calendar it touched)."""
    marker_at = clndr_data.find(_NESTED_MARKER)
    if 0 <= marker_at < _NESTED_MARKER_SEARCH_WINDOW:
        return _parse_clndr_data_nested(clndr_id, clndr_data[marker_at:], parse_log)
    return _parse_clndr_data_legacy(clndr_id, clndr_data, parse_log)


def _hours_per_day(row: dict, week: list[CalendarDay]) -> float:
    """The calendar's "Hours per Time Period → Day" — CALENDAR.day_hr_cnt, the
    exact divisor P6 itself uses to show every hour-stored duration and float
    in days (TASK.total_float_hr_cnt / day_hr_cnt, TASK.target_drtn_hr_cnt /
    day_hr_cnt). It's a setting in its own right, not derived from the shifts:
    a 08:00-17:00 week with a lunch break is 8h/day in P6, not the 9h a shift
    average gives. Only a file without the column (hand-built ones, very old
    exports) falls back to averaging the working days' shifts."""
    day_hr = _safe_float(row.get("day_hr_cnt", ""))
    if day_hr > 0:
        return day_hr
    working = [d.total_hours for d in week if d.is_working]
    return round(sum(working) / len(working), 4) if working else 8.0


# ---------------------------------------------------------------------------
# Table parsers
# ---------------------------------------------------------------------------


def _parse_projects(rows: list[dict]) -> list[ProjectMeta]:
    return [
        ProjectMeta(
            proj_id=r.get("proj_id", ""),
            proj_short_name=r.get("proj_short_name", ""),
            proj_name=r.get("proj_name", ""),
            data_date=_parse_date(r.get("last_recalc_date", "")),
            last_fin_date=_parse_date(r.get("last_fin_date", "")),
            plan_start_date=_parse_date(r.get("plan_start_date", "")),
            clndr_id=r.get("clndr_id") or None,
        )
        for r in rows
    ]


def _parse_wbs(rows: list[dict]) -> list[WbsNode]:
    return [
        WbsNode(
            wbs_id=r.get("wbs_id", ""),
            proj_id=r.get("proj_id", ""),
            parent_wbs_id=r.get("parent_wbs_id") or None,
            wbs_short_name=r.get("wbs_short_name", ""),
            wbs_name=r.get("wbs_name", ""),
            seq_num=_safe_int(r.get("seq_num", "")),
        )
        for r in rows
    ]


def _parse_calendars(rows: list[dict], proj_id: str, parse_log: list[str]) -> list[Calendar]:
    """Two-layer calendar priority: global calendars (no proj_id) loaded first,
    then project-specific calendars (proj_id matches) override by clndr_id."""
    cal_map: dict[str, Calendar] = {}
    for r in rows:
        if r.get("proj_id", "").strip():
            continue
        cid = r.get("clndr_id", "")
        week, exceptions = _parse_clndr_data(cid, r.get("clndr_data", ""), parse_log)
        cal_map[cid] = Calendar(
            clndr_id=cid,
            clndr_name=r.get("clndr_name", ""),
            default_work_week=week,
            exceptions=exceptions,
            hours_per_day=_hours_per_day(r, week),
        )
        parse_log.append(f"CAL {cid} ({r.get('clndr_name', '')}): loaded as GLOBAL")

    for r in rows:
        if r.get("proj_id", "").strip() != proj_id:
            continue
        cid = r.get("clndr_id", "")
        week, exceptions = _parse_clndr_data(cid, r.get("clndr_data", ""), parse_log)
        if cid in cal_map:
            parse_log.append(f"CAL {cid}: project-specific version OVERRIDES global for proj {proj_id}")
        else:
            parse_log.append(f"CAL {cid}: loaded as PROJECT-SPECIFIC for proj {proj_id}")
        cal_map[cid] = Calendar(
            clndr_id=cid,
            clndr_name=r.get("clndr_name", ""),
            default_work_week=week,
            exceptions=exceptions,
            hours_per_day=_hours_per_day(r, week),
        )

    return list(cal_map.values())


def _parse_tasks(rows: list[dict], parse_log: list[str]) -> list[Activity]:
    result = []
    for r in rows:
        raw_od = r.get("target_drtn_hr_cnt", "")
        raw_rd = r.get("remain_drtn_hr_cnt", "")
        od = _safe_float(raw_od)
        rd = _safe_float(raw_rd)
        tid = r.get("task_id", "?")

        if raw_od in (None, ""):
            parse_log.append(f"WARNING: TASK {tid}: target_drtn_hr_cnt is empty")
        if raw_rd in (None, ""):
            parse_log.append(f"WARNING: TASK {tid}: remain_drtn_hr_cnt is empty")

        activity = Activity(
            task_id=tid,
            proj_id=r.get("proj_id", ""),
            wbs_id=r.get("wbs_id") or None,
            clndr_id=r.get("clndr_id") or None,
            task_code=r.get("task_code", ""),
            task_name=r.get("task_name", ""),
            task_type=r.get("task_type", "TT_Task"),
            status_code=r.get("status_code", "TK_NotStart"),
            phys_complete_pct=_safe_float(r.get("phys_complete_pct", "0")),
            target_drtn_hr_cnt=od,
            remain_drtn_hr_cnt=rd,
        )
        activity.early_start_date = _parse_date(r.get("early_start_date", ""))
        activity.early_end_date = _parse_date(r.get("early_end_date", ""))
        activity.late_start_date = _parse_date(r.get("late_start_date", ""))
        activity.late_end_date = _parse_date(r.get("late_end_date", ""))
        activity.act_start_date = _parse_date(r.get("act_start_date", ""))
        activity.act_end_date = _parse_date(r.get("act_end_date", ""))
        activity.target_start_date = _parse_date(r.get("target_start_date", ""))
        activity.target_end_date = _parse_date(r.get("target_end_date", ""))
        activity.restart_date = _parse_date(r.get("restart_date", ""))
        activity.reend_date = _parse_date(r.get("reend_date", ""))
        activity.total_float_hr_cnt = (
            _safe_float(r.get("total_float_hr_cnt", "")) if r.get("total_float_hr_cnt", "") else None
        )
        activity.free_float_hr_cnt = (
            _safe_float(r.get("free_float_hr_cnt", "")) if r.get("free_float_hr_cnt", "") else None
        )
        activity.cstr_type = r.get("cstr_type") or None
        activity.cstr_date = _parse_date(r.get("cstr_date", ""))
        activity.cstr_type2 = r.get("cstr_type2") or None
        activity.cstr_date2 = _parse_date(r.get("cstr_date2", ""))
        activity.seq_num = _safe_int(r.get("seq_num", ""))
        result.append(activity)
    return result


def _parse_taskpred(rows: list[dict]) -> list[Relationship]:
    return [
        Relationship(
            task_pred_id=r.get("task_pred_id", ""),
            task_id=r.get("task_id", ""),
            pred_task_id=r.get("pred_task_id", ""),
            pred_type=r.get("pred_type", "PR_FS"),
            lag_hr_cnt=_safe_float(r.get("lag_hr_cnt", "0")),
        )
        for r in rows
    ]


def _parse_rsrc(rows: list[dict]) -> list[Resource]:
    return [
        Resource(
            rsrc_id=r.get("rsrc_id", ""),
            rsrc_name=r.get("rsrc_name", ""),
            rsrc_short_name=r.get("rsrc_short_name", ""),
            rsrc_type=r.get("rsrc_type", "RT_Labor"),
            unit_id=r.get("unit_id") or None,
            clndr_id=r.get("clndr_id") or None,
            curr_id=r.get("curr_id") or None,
        )
        for r in rows
    ]


def _parse_taskrsrc(rows: list[dict], known_rsrc_ids: set[str], parse_log: list[str]) -> list[ResourceAssignment]:
    result = []
    for r in rows:
        rsrc_id = r.get("rsrc_id", "")
        if rsrc_id not in known_rsrc_ids:
            msg = f"TASKRSRC {r.get('taskrsrc_id', '?')}: references unknown rsrc_id {rsrc_id!r} — skipped"
            logger.warning(msg)
            parse_log.append(f"WARNING: {msg}")
            continue
        result.append(
            ResourceAssignment(
                taskrsrc_id=r.get("taskrsrc_id", ""),
                task_id=r.get("task_id", ""),
                rsrc_id=rsrc_id,
                remain_qty=_safe_float(r.get("remain_qty", "0")),
                target_qty=_safe_float(r.get("target_qty", "0")),
                act_reg_qty=_safe_float(r.get("act_reg_qty", "0")),
                target_cost=_safe_float(r.get("target_cost", "0")),
                act_reg_cost=_safe_float(r.get("act_reg_cost", "0")),
                remain_cost=_safe_float(r.get("remain_cost", "0")),
                unit_id=r.get("unit_id") or None,
            )
        )
    return result


def _parse_actvtype(rows: list[dict]) -> list[CodeType]:
    return [
        CodeType(
            actv_code_type_id=r.get("actv_code_type_id", ""),
            actv_code_type=r.get("actv_code_type", ""),
            proj_id=r.get("proj_id") or None,
        )
        for r in rows
    ]


def _parse_actvcode(rows: list[dict]) -> list[CodeValue]:
    return [
        CodeValue(
            actv_code_id=r.get("actv_code_id", ""),
            actv_code_type_id=r.get("actv_code_type_id", ""),
            actv_code_name=r.get("actv_code_name", ""),
            short_name=r.get("short_name", ""),
            parent_actv_code_id=r.get("parent_actv_code_id") or None,
            seq_num=_safe_int(r.get("seq_num", "")),
        )
        for r in rows
    ]


def _parse_taskactv(rows: list[dict]) -> list[ActivityCode]:
    return [
        ActivityCode(
            task_id=r.get("task_id", ""),
            actv_code_type_id=r.get("actv_code_type_id", ""),
            actv_code_id=r.get("actv_code_id", ""),
        )
        for r in rows
    ]


def main_project_id(project_rows: list[dict]) -> str:
    """The proj_id of the project this file is ABOUT.

    A P6 export can carry more than one project. The common case is "export
    with baselines": the baselines ride along as extra PROJECT rows with
    `export_flag` N and `orig_proj_id` pointing back at the real project, and
    every TASK / PROJWBS / TASKPRED / TASKRSRC row of theirs is written too —
    with the SAME task_codes as the live programme, since a baseline is a copy
    of it. Pick the first project that is neither; fall back to the first row
    for files that don't carry the flags at all."""
    for r in project_rows:
        if r.get("export_flag", "Y").strip().upper() != "N" and not r.get("orig_proj_id", "").strip():
            return r.get("proj_id", "")
    return project_rows[0].get("proj_id", "") if project_rows else ""


def _only_main_project(tables: dict[str, list[dict]], proj_id: str, parse_log: list[str]) -> dict[str, list[dict]]:
    """Drop every row that belongs to another project in the file (see
    `main_project_id`). Without this a baseline exported alongside the
    programme merged into it: its rows share task_codes with the live ones, so
    whichever came last in the file won — not-started baseline copies
    overwriting progressed activities, and both networks fed to one CPM run."""
    other_projects = [r.get("proj_id", "") for r in tables.get("PROJECT", []) if r.get("proj_id", "") != proj_id]
    if not other_projects:
        return tables
    parse_log.append(
        f"File carries {len(other_projects)} other project(s) {other_projects} (baselines or companions) "
        f"— reading only proj_id {proj_id}"
    )

    out = dict(tables)
    out["PROJECT"] = [r for r in tables.get("PROJECT", []) if r.get("proj_id", "") == proj_id]
    out["PROJWBS"] = [r for r in tables.get("PROJWBS", []) if r.get("proj_id", "") == proj_id]
    out["TASK"] = [r for r in tables.get("TASK", []) if r.get("proj_id", "") == proj_id]
    task_ids = {r.get("task_id", "") for r in out["TASK"]}
    out["TASKPRED"] = [
        r for r in tables.get("TASKPRED", []) if r.get("task_id", "") in task_ids and r.get("pred_task_id", "") in task_ids
    ]
    out["TASKRSRC"] = [r for r in tables.get("TASKRSRC", []) if r.get("task_id", "") in task_ids]
    out["TASKACTV"] = [r for r in tables.get("TASKACTV", []) if r.get("task_id", "") in task_ids]
    # Global code types (no proj_id) stay; project-scoped ones only for ours.
    out["ACTVTYPE"] = [r for r in tables.get("ACTVTYPE", []) if r.get("proj_id", "").strip() in ("", proj_id)]
    type_ids = {r.get("actv_code_type_id", "") for r in out["ACTVTYPE"]}
    out["ACTVCODE"] = [r for r in tables.get("ACTVCODE", []) if r.get("actv_code_type_id", "") in type_ids]
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_xer(file_bytes: bytes) -> ParsedSchedule:
    """Parse a `.xer` file's raw bytes into a `ParsedSchedule`.

    Raises `XerParseError` if the file is too large, has no PROJECT table, or
    otherwise can't be parsed.
    """
    if len(file_bytes) > MAX_FILE_BYTES:
        raise XerParseError(
            f"File too large: {len(file_bytes) / 1024 / 1024:.1f} MB "
            f"(limit {MAX_FILE_BYTES // 1024 // 1024} MB)"
        )

    parse_log: list[str] = [f"parse_xer started: size={len(file_bytes)} bytes"]
    text = _decode(file_bytes)
    tables = _read_tables(text, parse_log)

    if not tables.get("PROJECT"):
        raise XerParseError("No PROJECT table found in this file")
    tables = _only_main_project(tables, main_project_id(tables["PROJECT"]), parse_log)

    projects = _parse_projects(tables.get("PROJECT", []))
    if not projects:
        raise XerParseError("No PROJECT table found in this file")
    meta = projects[0]
    parse_log.append(f"Project: {meta.proj_name!r}, data_date={meta.data_date}")

    calendars = _parse_calendars(tables.get("CALENDAR", []), meta.proj_id, parse_log)
    if not calendars:
        parse_log.append("WARNING: No CALENDAR table found — using default 5-day/8h fallback")
        from app.parser._default_calendar import make_default_calendar

        calendars = [make_default_calendar()]

    wbs_nodes = _parse_wbs(tables.get("PROJWBS", []))
    activities = _parse_tasks(tables.get("TASK", []), parse_log)
    relationships = _parse_taskpred(tables.get("TASKPRED", []))
    resources = _parse_rsrc(tables.get("RSRC", []))
    known_rsrc_ids = {r.rsrc_id for r in resources}
    assignments = _parse_taskrsrc(tables.get("TASKRSRC", []), known_rsrc_ids, parse_log)
    code_types = _parse_actvtype(tables.get("ACTVTYPE", []))
    code_values = _parse_actvcode(tables.get("ACTVCODE", []))
    activity_codes = _parse_taskactv(tables.get("TASKACTV", []))

    parse_log.append(
        f"Parse complete: {len(activities)} activities, {len(relationships)} relationships, "
        f"{len(calendars)} calendars, {len(wbs_nodes)} WBS nodes, {len(resources)} resources, "
        f"{len(assignments)} resource assignments, {len(code_values)} activity code values"
    )
    logger.info(parse_log[-1])

    return ParsedSchedule(
        meta=meta,
        wbs_nodes=wbs_nodes,
        calendars=calendars,
        activities=activities,
        relationships=relationships,
        resources=resources,
        assignments=assignments,
        code_types=code_types,
        code_values=code_values,
        activity_codes=activity_codes,
        parse_log=parse_log,
    )
