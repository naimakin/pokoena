"""Round trip on a REAL P6 export: read it, record progress, write it back.

Skipped unless POKO_REAL_XER names one or more .xer files (os.pathsep-
separated) — real client programmes don't belong in the repo, but the check
has to run against them, because the synthetic fixtures carry none of the
conventions P6 actually writes. Run with -s for the report:

    POKO_REAL_XER="C:/path/a.xer;C:/path/b.xer" pytest tests/test_real_xer_roundtrip.py -s

With no Primavera to open the export in, "would P6 read this right" is checked
against the conventions P6 itself follows in the files it writes (measured on
real exports — every one of these holds on 100% of the rows P6 produced):

  TASK      TK_NotStart  no actual dates
            TK_Active    act_start_date, no act_end_date
            TK_Complete  both actual dates (a milestone's two are the same
                         instant), remain_drtn_hr_cnt 0, phys_complete_pct 100,
                         blank total/free float, blank restart/reend dates
            act_work_qty = sum of its RT_Labor assignments' act_reg + act_ot
  TASKRSRC  actual dates = its activity's; on a completed activity
            act_reg_qty = target_qty, remain_qty 0, blank restart/reend
  P6 shows % by TASK.complete_pct_type: CP_Phys -> phys_complete_pct,
            CP_Drtn -> duration %, CP_Units -> act / target work units

Phases: (1) what Poko reads vs what P6 shows, (2) progress entered through
the API on every kind of activity the file has, (3) the export checked
against the rules above and byte-compared outside the edited rows,
(4) the export re-imported, (5) Poko's CPM run over the export (the nearest
thing to P6's F9 available here).
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.engine.cpm.scheduler import schedule
from app.engine.export.xer_progress import decode_xer
from app.parser.xer_parser import main_project_id, parse_xer
from tests.factories import add_membership, create_project, create_tenant, create_user
from app.models.user_tenant_role import TenantRole

PATHS = [p for p in os.environ.get("POKO_REAL_XER", "").split(os.pathsep) if p.strip()]

pytestmark = pytest.mark.skipif(not PATHS, reason="POKO_REAL_XER not set")

MILESTONES = {"TT_Mile", "TT_FinMile"}
STATUS = {"TK_NotStart": "not_started", "TK_Active": "in_progress", "TK_Complete": "complete"}


# --- reading the file ----------------------------------------------------------


def _tables(raw: bytes) -> dict[str, list[dict[str, str]]]:
    text, _ = decode_xer(raw)
    out: dict[str, list[dict[str, str]]] = {}
    current, cols = None, []
    for line in text.split("\n"):
        line = line.rstrip("\r")
        if line.startswith("%T\t"):
            current = line.split("\t")[1]
            out.setdefault(current, [])
        elif line.startswith("%F\t"):
            cols = line.split("\t")[1:]
        elif line.startswith("%R\t"):
            out[current].append(dict(zip(cols, line.split("\t")[1:])))
    return out


def _f(v: str | None) -> float:
    try:
        return float(v or 0)
    except ValueError:
        return 0.0


def _d(v: str | None) -> date | None:
    return datetime.strptime(v[:10], "%Y-%m-%d").date() if v else None


class Programme:
    """The main project's TASK / TASKRSRC rows, with labor resources known."""

    def __init__(self, raw: bytes):
        self.raw = raw
        self.t = _tables(raw)
        proj = main_project_id(self.t.get("PROJECT", []))
        self.tasks = {r["task_id"]: r for r in self.t.get("TASK", []) if r.get("proj_id") in ("", proj)}
        self.by_code = {r["task_code"]: r for r in self.tasks.values()}
        rsrc_type = {r["rsrc_id"]: r.get("rsrc_type", "") for r in self.t.get("RSRC", [])}
        self.assignments: dict[str, list[dict]] = {}
        for a in self.t.get("TASKRSRC", []):
            if a["task_id"] in self.tasks:
                a["_type"] = a.get("rsrc_type") or rsrc_type.get(a["rsrc_id"], "")
                self.assignments.setdefault(a["task_id"], []).append(a)
        self.hpd = {c["clndr_id"]: _f(c.get("day_hr_cnt")) or 8.0 for c in self.t.get("CALENDAR", [])}

    def labor(self, task_id: str) -> list[dict]:
        return [a for a in self.assignments.get(task_id, []) if a["_type"] == "RT_Labor"]

    def p6_shown_pct(self, r: dict) -> float:
        kind = r.get("complete_pct_type", "CP_Phys")
        if r["status_code"] == "TK_Complete" and kind != "CP_Units":
            return 100.0
        if kind == "CP_Drtn":
            target = _f(r["target_drtn_hr_cnt"])
            return 0.0 if target <= 0 else (target - _f(r["remain_drtn_hr_cnt"])) / target * 100
        if kind == "CP_Units":
            target = _f(r.get("target_work_qty")) + _f(r.get("target_equip_qty"))
            act = _f(r.get("act_work_qty")) + _f(r.get("act_equip_qty"))
            return 0.0 if target <= 0 else act / target * 100
        return _f(r["phys_complete_pct"])


# --- the run ---------------------------------------------------------------------


class Report:
    def __init__(self, name: str):
        self.name = name
        self.lines: list[str] = []
        self.failures: list[str] = []

    def info(self, msg: str) -> None:
        self.lines.append(f"  {msg}")

    def check(self, ok: bool, msg: str) -> None:
        self.lines.append(f"  {'PASS' if ok else 'FAIL'}  {msg}")
        if not ok:
            self.failures.append(msg)

    def print(self) -> None:
        print(f"\n===== {self.name} =====")
        print("\n".join(self.lines))


def _login_admin(client, db_session):
    tenant = create_tenant(db_session, name="Roundtrip", slug="roundtrip")
    user = create_user(db_session, "rt-admin@example.com", "secret123")
    add_membership(db_session, user, tenant, TenantRole.company_admin)
    client.post("/auth/login", json={"email": "rt-admin@example.com", "password": "secret123"})
    return tenant


def _import(client, project_id, raw: bytes, name: str):
    r = client.post(
        f"/projects/{project_id}/schedule-imports",
        params={"force": "true"},
        files={"file": (name, raw, "application/octet-stream")},
    )
    assert r.status_code == 201, r.text


def _activities(client, project_id) -> dict[str, dict]:
    return {a["external_id"]: a for a in client.get(f"/activities?project_id={project_id}").json()}


def _pick(prog: Programme, task_type: str, status: str, labor: bool | None, taken: set[str]) -> dict | None:
    for r in prog.tasks.values():
        if r["task_code"] in taken or r["task_type"] != task_type or r["status_code"] != status:
            continue
        if labor is not None and bool(prog.labor(r["task_id"])) != labor:
            continue
        if labor and not any(_f(a["target_qty"]) > 0 for a in prog.labor(r["task_id"])):
            continue
        if task_type == "TT_Task" and _f(r["target_drtn_hr_cnt"]) <= 0:
            continue
        taken.add(r["task_code"])
        return r
    return None


@pytest.mark.parametrize("path", PATHS, ids=[Path(p).name for p in PATHS])
def test_real_xer_roundtrip(path, client, db_session):
    rep = Report(Path(path).name)
    raw = Path(path).read_bytes()
    prog = Programme(raw)
    parsed = parse_xer(raw)
    dd = parsed.meta.data_date.date() if parsed.meta.data_date else date.today()
    rep.info(f"{len(prog.tasks)} activities, data date {dd}, {sum(map(len, prog.assignments.values()))} assignments")

    tenant = _login_admin(client, db_session)
    project = create_project(db_session, tenant)
    _import(client, project.id, raw, Path(path).name)
    acts = _activities(client, project.id)

    # ---- (1) reading ------------------------------------------------------
    rep.info("--- (1) What Poko reads vs what P6 shows")
    missing = [c for c in prog.by_code if c not in acts]
    rep.check(not missing, f"every TASK row imported ({len(missing)} missing)")
    status_bad, float_bad, date_bad, pct_bad = [], [], [], []
    for code, r in prog.by_code.items():
        a = acts.get(code)
        if a is None:
            continue
        if a["status"] != STATUS.get(r["status_code"]):
            status_bad.append(code)
        tf = r.get("total_float_hr_cnt", "")
        if (a["total_float_hours"] is None) != (tf == "") or (tf and abs(a["total_float_hours"] - _f(tf)) > 0.01):
            float_bad.append(f"{code}: file {tf!r} poko {a['total_float_hours']}")
        hpd = prog.hpd.get(r["clndr_id"])
        if hpd and abs(a["hours_per_day"] - hpd) > 0.001:
            float_bad.append(f"{code}: day_hr_cnt {hpd} poko {a['hours_per_day']}")
        if (a["early_start"] or None) != (r["early_start_date"][:10] or None) or (a["early_finish"] or None) != (
            r["early_end_date"][:10] or None
        ):
            date_bad.append(code)
        shown = prog.p6_shown_pct(r)
        if abs(a["percent_complete"] - shown) > 1:
            pct_bad.append((code, r.get("complete_pct_type"), round(shown), a["percent_complete"], bool(prog.labor(r["task_id"]))))
    rep.check(not status_bad, f"status matches status_code ({len(status_bad)} differ) {status_bad[:5]}")
    rep.check(not float_bad, f"total float = TASK.total_float_hr_cnt, day = CALENDAR.day_hr_cnt ({len(float_bad)} differ) {float_bad[:3]}")
    rep.check(not date_bad, f"early start/finish = TASK.early_*_date ({len(date_bad)} differ) {date_bad[:5]}")
    # Informational, not a failure: Poko shows % by the planning team's rule
    # (labor units %, else duration %), which by design differs from P6's
    # complete_pct_type-driven % on activities whose units/duration aren't
    # maintained (services/activity_progress.py).
    rep.info(
        f"INFO  % Poko shows vs % P6 shows (by complete_pct_type): {len(pct_bad)} differ; "
        f"sample (code, pct_type, P6 %, Poko %, labor?): {pct_bad[:5]}"
    )

    # ---- (2) progress --------------------------------------------------------
    rep.info("--- (2) Progress entered in Poko")
    taken: set[str] = set()
    start = dd - timedelta(days=10)
    finish = dd - timedelta(days=2)
    plan = [
        ("NotStart task, no labor: start + 40%", ("TT_Task", "TK_NotStart", False), {"actual_start": start, "percent_complete": 40}),
        ("NotStart task, labor: start + 40%", ("TT_Task", "TK_NotStart", True), {"actual_start": start, "percent_complete": 40}),
        ("NotStart task, no labor: % only (no date)", ("TT_Task", "TK_NotStart", False), {"percent_complete": 30}),
        ("NotStart task: start + finish", ("TT_Task", "TK_NotStart", None), {"actual_start": start, "actual_finish": finish}),
        ("Active task, no labor: % to 70", ("TT_Task", "TK_Active", False), {"percent_complete": 70}),
        ("Active task, labor: % to 70", ("TT_Task", "TK_Active", True), {"percent_complete": 70}),
        ("Active task, labor: finish", ("TT_Task", "TK_Active", True), {"actual_finish": finish}),
        ("Active task, no labor: finish", ("TT_Task", "TK_Active", False), {"actual_finish": finish}),
        ("Complete task, labor: clear dates (undo)", ("TT_Task", "TK_Complete", True), {"actual_start": None, "actual_finish": None}),
        ("Finish milestone: actual finish", ("TT_FinMile", "TK_NotStart", None), {"actual_finish": finish}),
        ("Start milestone: actual start", ("TT_Mile", "TK_NotStart", None), {"actual_start": start}),
    ]
    edited: dict[str, tuple[str, dict, dict]] = {}
    for label, (tt, st, labor), payload in plan:
        r = _pick(prog, tt, st, labor, taken)
        if r is None:
            rep.info(f"skip   {label} — no such activity in this file")
            continue
        a = acts[r["task_code"]]
        if "actual_finish" in payload and "actual_start" not in payload and tt == "TT_Task":
            # finishing an in-progress activity: never before its own start
            own = _d(a["actual_start"]) or start
            payload = {**payload, "actual_finish": max(finish, own)}
        body = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in payload.items()}
        resp = client.patch(f"/activities/{a['id']}", json=body)
        rep.check(resp.status_code == 200, f"{label} [{r['task_code']}] -> HTTP {resp.status_code} {resp.text[:120] if resp.status_code != 200 else ''}")
        if resp.status_code == 200:
            edited[r["task_code"]] = (label, r, resp.json())

    # ---- (3) export ----------------------------------------------------------
    rep.info("--- (3) Export checked against P6's conventions")
    exp = client.get(f"/projects/{project.id}/export/xer")
    rep.check(exp.status_code == 200, "export downloads")
    out = Programme(exp.content)
    rep.check(len(out.tasks) == len(prog.tasks), f"same TASK row count ({len(out.tasks)} vs {len(prog.tasks)})")

    for code, (label, before, poko) in edited.items():
        r = out.by_code[code]
        sc, tt = r["status_code"], r["task_type"]
        want_sc = {"not_started": "TK_NotStart", "in_progress": "TK_Active", "complete": "TK_Complete"}[poko["status"]]
        problems = []
        if sc != want_sc:
            problems.append(f"status_code {sc} != {want_sc}")
        if sc == "TK_NotStart" and (r["act_start_date"] or r["act_end_date"]):
            problems.append("not started but has actual dates")
        if sc == "TK_Active" and (not r["act_start_date"] or r["act_end_date"]):
            problems.append(f"active needs act_start only (start={r['act_start_date']!r} end={r['act_end_date']!r})")
        if sc == "TK_Complete":
            if not r["act_start_date"] or not r["act_end_date"]:
                problems.append(f"complete needs both actual dates (start={r['act_start_date']!r} end={r['act_end_date']!r})")
            if tt in MILESTONES and r["act_start_date"] != r["act_end_date"]:
                problems.append("milestone's two actual dates differ")
            if _f(r["remain_drtn_hr_cnt"]) != 0:
                problems.append(f"remain_drtn {r['remain_drtn_hr_cnt']}")
            if _f(r["phys_complete_pct"]) != 100:
                problems.append(f"phys {r['phys_complete_pct']}")
            if r.get("total_float_hr_cnt") or r.get("free_float_hr_cnt"):
                problems.append(f"float not blank ({r.get('total_float_hr_cnt')!r}/{r.get('free_float_hr_cnt')!r})")
            if r.get("restart_date") or r.get("reend_date"):
                problems.append("restart/reend not blank")
        if r["act_start_date"] and r["act_end_date"] and r["act_start_date"] > r["act_end_date"]:
            problems.append("act_start after act_end")
        for col in ("act_start_date", "act_end_date"):
            if r[col] and _d(r[col]) > dd:
                problems.append(f"{col} after data date")
        # what P6 will show as %
        shown = out.p6_shown_pct(r)
        if abs(shown - poko["percent_complete"]) > 1:
            problems.append(f"P6 will show {shown:.0f}% ({r.get('complete_pct_type')}), Poko shows {poko['percent_complete']}%")
        # units
        labor = out.labor(r["task_id"])
        if labor and "act_work_qty" in r:
            s = sum(_f(a["act_reg_qty"]) + _f(a.get("act_ot_qty")) for a in labor)
            if abs(_f(r["act_work_qty"]) - s) > 0.01:
                problems.append(f"act_work_qty {r['act_work_qty']} != labor act sum {s:g}")
        for a in labor:
            if abs(_f(a["act_reg_qty"]) + _f(a.get("act_ot_qty")) + _f(a["remain_qty"]) - _f(a["target_qty"])) > 0.01:
                problems.append(f"TASKRSRC {a['taskrsrc_id']}: act+remain != target")
            if sc == "TK_Complete" and (_f(a["remain_qty"]) != 0 or a.get("restart_date") or a.get("reend_date")):
                problems.append(f"TASKRSRC {a['taskrsrc_id']}: complete but remain/restart left")
        for a in out.assignments.get(r["task_id"], []):
            for col in ("act_start_date", "act_end_date"):
                if col in a and a[col] != r[col]:
                    problems.append(f"TASKRSRC {a['taskrsrc_id']} {col} {a[col]!r} != TASK {r[col]!r}")
        rep.check(not problems, f"{label} [{code}] {sc} phys={r['phys_complete_pct']} remain={r['remain_drtn_hr_cnt']}h " + "; ".join(problems))

    # untouched rows: byte-identical
    edited_ids = {before["task_id"] for _, before, _ in edited.values()}
    changed = [
        r["task_code"]
        for tid, r in out.tasks.items()
        if tid not in edited_ids and {k: v for k, v in r.items() if not k.startswith("_")} != {k: v for k, v in prog.tasks[tid].items() if not k.startswith("_")}
    ]
    rep.check(not changed, f"untouched TASK rows passed through unchanged ({len(changed)} changed) {changed[:5]}")
    other_tables = [name for name in prog.t if name not in ("TASK", "TASKRSRC") and prog.t[name] != out.t.get(name)]
    rep.check(not other_tables, f"all other tables identical {other_tables}")

    # ---- (4) re-import --------------------------------------------------------
    rep.info("--- (4) Export re-imported into Poko")
    project2 = create_project(db_session, tenant)
    _import(client, project2.id, exp.content, "roundtrip.xer")
    acts2 = _activities(client, project2.id)
    for code, (label, _, poko) in edited.items():
        b = acts2[code]
        same = all(b[k] == poko[k] for k in ("status", "percent_complete", "actual_start", "actual_finish"))
        rep.check(same, f"{label} [{code}] reads back the same " + (
            "" if same else str({k: (poko[k], b[k]) for k in ("status", "percent_complete", "actual_start", "actual_finish") if b[k] != poko[k]})
        ))

    # ---- (5) reschedule --------------------------------------------------------
    rep.info("--- (5) Poko's CPM over the export (stand-in for P6 F9)")
    reparsed = parse_xer(exp.content)
    try:
        schedule(reparsed)
        rep.check(True, "export schedules without errors")
    except Exception as e:  # noqa: BLE001
        rep.check(False, f"export schedules without errors: {e}")
    by_code = {a.task_code: a for a in reparsed.activities}
    for code, (label, _, poko) in edited.items():
        a = by_code[code]
        notes = []
        if poko["status"] == "in_progress":
            if a.early_start_date and a.act_start_date and a.early_start_date != a.act_start_date:
                notes.append("start != actual start")
            if a.early_end_date and a.early_end_date.date() < dd:
                notes.append(f"finish {a.early_end_date.date()} before data date")
        if poko["status"] == "complete" and a.early_end_date != a.act_end_date:
            notes.append("finish != actual finish")
        rep.check(not notes, f"{label} [{code}] start {a.early_start_date} finish {a.early_end_date} " + "; ".join(notes))

    rep.print()
    assert not rep.failures, f"{len(rep.failures)} check(s) failed — see report"
