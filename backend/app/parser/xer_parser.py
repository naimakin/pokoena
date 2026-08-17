"""Parses a Primavera P6 `.xer` file into the canonical dataclasses in
`xer_models.py`. Ported from a colleague's reference P6 desktop app
(`backend/app/parser/xer_parser.py` there), with two changes:

1. Takes raw `bytes` rather than a filesystem `Path` — this service has no local
   disk to read from (and shouldn't; see `services/xer_import.py` for where the
   result actually lands: Postgres, not a JSON file).
2. Trimmed to what CPM scheduling needs: WBS names (for display), calendars,
   activities, and relationships. Activity codes, code types, and resource
   assignments from the original parser are not ported this slice — nothing in
   CPM scheduling reads them, and nothing in this app displays them yet.

Encoding strategy: try UTF-8 first, fall back to latin-1 (Windows-1252), same as
the reference. Everything else — the multi-version `clndr_data` tokenizer, the
two-layer (global vs. project-specific) calendar priority, the audit-trail
`parse_log` — is unchanged.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, time
from typing import Optional

from app.parser.xer_models import (
    Activity,
    Calendar,
    CalendarDay,
    CalendarException,
    DayShift,
    ParsedSchedule,
    ProjectMeta,
    Relationship,
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


def _parse_clndr_data(
    clndr_id: str, clndr_data: str, parse_log: list[str]
) -> tuple[list[CalendarDay], list[CalendarException]]:
    """Parse a P6 `clndr_data` field (supports v7-v24 format variants). Unknown
    tokens produce a warning + parse_log entry rather than a silent error.

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


def _hours_per_day(week: list[CalendarDay]) -> float:
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
            hours_per_day=_hours_per_day(week),
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
            hours_per_day=_hours_per_day(week),
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

    parse_log.append(
        f"Parse complete: {len(activities)} activities, {len(relationships)} relationships, "
        f"{len(calendars)} calendars, {len(wbs_nodes)} WBS nodes"
    )
    logger.info(parse_log[-1])

    return ParsedSchedule(
        meta=meta,
        wbs_nodes=wbs_nodes,
        calendars=calendars,
        activities=activities,
        relationships=relationships,
        parse_log=parse_log,
    )
