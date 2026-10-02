"""Calendar-aware Forward Pass + Backward Pass + float calculation + longest-path
critical-path determination. Ported from the reference project's `scheduler.py`,
unchanged algorithmically — only the import path (`app.parser.xer_models`) and
the container type (`ParsedSchedule` instead of `ProjectSnapshot`) differ, plus
`tf_days`/`ff_days`/`lp_critical` are now plain dataclass fields on `Activity`
(see `xer_models.py`) rather than ad hoc `__dict__` entries.

Rules:
  - Retained Logic for TK_Active (out-of-sequence handled)
  - Duration fields are NEVER modified (read-only)
  - All date/float fields are written back to Activity objects in-place
  - Lag uses the predecessor's calendar
  - Milestone types (TT_Mile, TT_FinMile, TT_StartMile) handled separately
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from typing import Optional

from app.engine.cpm.calendar_engine import CalendarEngine
from app.parser.xer_models import Activity, ParsedSchedule, Relationship

logger = logging.getLogger(__name__)

_MILESTONE_TYPES = {"TT_Mile", "TT_FinMile", "TT_StartMile"}
_TOL = 0.01  # hours — float tolerance for critical path


class CpmCycleError(ValueError):
    """The activity network contains a cycle — CPM can't be run on it."""


# ---------------------------------------------------------------------------
# Topological sort (Kahn's algorithm)
# ---------------------------------------------------------------------------


def _topo_sort(task_ids: list[str], relationships: list[Relationship]) -> list[str]:
    """Return activities in topological order (predecessors before successors).
    Raises CpmCycleError if a cycle is detected."""
    in_degree: dict[str, int] = {tid: 0 for tid in task_ids}
    adj: dict[str, list[str]] = {tid: [] for tid in task_ids}

    for rel in relationships:
        if rel.pred_task_id in in_degree and rel.task_id in in_degree:
            adj[rel.pred_task_id].append(rel.task_id)
            in_degree[rel.task_id] += 1

    # Deterministic order — sort initial zero-degree nodes by task_id.
    queue = deque(sorted(tid for tid, deg in in_degree.items() if deg == 0))
    order: list[str] = []

    while queue:
        tid = queue.popleft()
        order.append(tid)
        new_zeros: list[str] = []
        for succ in adj[tid]:
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                new_zeros.append(succ)
        for z in sorted(new_zeros):
            queue.append(z)

    if len(order) != len(task_ids):
        raise CpmCycleError(
            f"Cycle detected in project network. Processed {len(order)} of {len(task_ids)} activities."
        )

    return order


# ---------------------------------------------------------------------------
# Constraint helpers
# ---------------------------------------------------------------------------

# P6's own codes, as they appear in a .xer's TASK.cstr_type: the "A"/"B"
# suffixes are "on or After" / "on or Before", and the mandatory pair is
# spelled out. CS_MSOA / CS_MEOA used to be read here as MANDATORY start /
# finish. They are the soft floors "start / finish on or after": treating a
# floor as a hard date pinned the late finish to it, so any activity logic
# pushed past its "finish on or after" date showed negative float that P6
# itself doesn't show. (CS_MSON / CS_MEON never appear in a P6 export; kept
# only so older hand-built fixtures keep their meaning.)
_SNET_TYPES = {"CS_MSOA", "CS_MSO", "CS_MSON"}  # Start On or After / Start On
_SNLT_TYPES = {"CS_MSOB", "CS_MSO"}  # Start On or Before / Start On
_FNET_TYPES = {"CS_MEOA", "CS_MEO", "CS_MEON"}  # Finish On or After / Finish On
_FNLT_TYPES = {"CS_MEOB", "CS_MEO"}  # Finish On or Before / Finish On
_MAND_START = {"CS_MANDSTART"}  # Mandatory Start
_MAND_FINISH = {"CS_MANDFIN"}  # Mandatory Finish
_ALAP = {"CS_ALAP"}  # As Late As Possible


def _parse_constraints(act: Activity) -> dict:
    snet = snlt = fnet = fnlt = mand_start = mand_finish = None
    alap = False

    for ctype, cdate in [(act.cstr_type, act.cstr_date), (act.cstr_type2, act.cstr_date2)]:
        if not ctype or not cdate:
            continue
        if ctype in _ALAP:
            alap = True
        elif ctype in _SNET_TYPES:
            snet = max(snet, cdate) if snet else cdate
        elif ctype in _SNLT_TYPES:
            snlt = min(snlt, cdate) if snlt else cdate
        elif ctype in _FNET_TYPES:
            fnet = max(fnet, cdate) if fnet else cdate
        elif ctype in _FNLT_TYPES:
            fnlt = min(fnlt, cdate) if fnlt else cdate
        elif ctype in _MAND_START:
            mand_start = cdate
        elif ctype in _MAND_FINISH:
            mand_finish = cdate

    return dict(
        snet=snet, snlt=snlt, fnet=fnet, fnlt=fnlt, mand_start=mand_start, mand_finish=mand_finish, alap=alap
    )


# ---------------------------------------------------------------------------
# Main scheduler
# ---------------------------------------------------------------------------


def _bound(cal: CalendarEngine, base: datetime, lag_h: float) -> datetime:
    return cal.add_work_hours(base, lag_h) if lag_h >= 0 else cal.sub_work_hours(base, -lag_h)


def schedule(parsed: ParsedSchedule, *, retained_logic: bool = False) -> ParsedSchedule:
    """Run CPM on the parsed schedule. Modifies Activity.early_*/late_*/float
    fields (and tf_days/ff_days/lp_critical/driven_by/driving_rels) in-place.
    Returns the same object.

    `retained_logic=False` is the engine as ported: an in-progress activity's
    remaining work runs from the data date whatever its predecessors are doing
    (in effect P6's Progress Override), and a finished predecessor binds at its
    actual dates even when they fall after the data date. Import uses it - its
    output only stands where P6 left a file unscheduled (services/xer_import.py),
    and it feeds the stored longest path.

    `retained_logic=True` is P6's default scheduling option, the one every real
    export we have was scheduled with: remaining work waits for unfinished
    predecessors (Activity.restart_date is where it resumes), finished work
    never pushes anything past the data date, and an in-progress activity's
    total float is late finish - early finish. Schedule Simulation uses it."""
    acts: dict[str, Activity] = {a.task_id: a for a in parsed.activities}
    rels: list[Relationship] = parsed.relationships

    cal_map: dict[str, CalendarEngine] = {}
    default_cal: Optional[CalendarEngine] = None
    for cal in parsed.calendars:
        eng = CalendarEngine(cal)
        cal_map[cal.clndr_id] = eng
        if cal.clndr_id == (parsed.meta.clndr_id or ""):
            default_cal = eng
    if default_cal is None and cal_map:
        default_cal = next(iter(cal_map.values()))

    def get_cal(clndr_id: Optional[str]) -> CalendarEngine:
        if clndr_id and clndr_id in cal_map:
            return cal_map[clndr_id]
        if default_cal:
            return default_cal
        raise RuntimeError("No calendar available")

    dd: datetime = parsed.meta.data_date or datetime.utcnow()

    pred_adj: dict[str, list[tuple[str, str, float]]] = {tid: [] for tid in acts}
    succ_adj: dict[str, list[tuple[str, str, float]]] = {tid: [] for tid in acts}

    for rel in rels:
        if rel.pred_task_id in acts and rel.task_id in acts:
            pred_adj[rel.task_id].append((rel.pred_task_id, rel.pred_type, rel.lag_hr_cnt))
            succ_adj[rel.pred_task_id].append((rel.task_id, rel.pred_type, rel.lag_hr_cnt))

    order = _topo_sort(list(acts.keys()), rels)

    must_finish_by: Optional[datetime] = parsed.meta.last_fin_date

    # Remaining hours each activity is scheduled with - its remaining duration,
    # unless an Expected Finish resized it. The backward pass reuses them.
    drtn_of: dict[str, float] = {}

    def remaining_start(a: Activity) -> Optional[datetime]:
        """Where the activity's remaining work starts: its early start, or for
        in-progress work under Retained Logic, where that work resumes."""
        if retained_logic and a.status_code == "TK_Active" and a.restart_date:
            return a.restart_date
        return a.early_start_date

    # -------------------------------------------------------------------------
    # FORWARD PASS
    # -------------------------------------------------------------------------
    for tid in order:
        act = acts[tid]
        c = get_cal(act.clndr_id)
        cstr = _parse_constraints(act)
        is_milestone = act.task_type in _MILESTONE_TYPES
        act.driving_rels = []

        if act.status_code == "TK_Complete":
            act.early_start_date = act.act_start_date
            act.early_end_date = act.act_end_date
            act.driven_by = "actual"
            drtn_of[tid] = 0.0
            continue

        drtn = act.remain_drtn_hr_cnt or 0.0

        if act.status_code == "TK_Active":
            act.early_start_date = act.act_start_date or dd
            start_ties: list[tuple[str, str, float]] = []
            finish_ties: list[tuple[str, str, float]] = []
            finish_floor: Optional[datetime] = None
            if not retained_logic:
                rs = dd
            else:
                # Retained Logic: the remaining work waits for every
                # predecessor that hasn't finished.
                start_bounds: list[tuple[datetime, str, str, float]] = []
                finish_bounds: list[tuple[datetime, str, str, float]] = []
                for pred_id, rel_type, lag_h in pred_adj[tid]:
                    pred = acts[pred_id]
                    if pred.status_code == "TK_Complete":
                        continue
                    pES = pred.early_start_date or dd
                    pEF = pred.early_end_date or pES
                    t = _bound(get_cal(pred.clndr_id), pEF if rel_type in ("PR_FS", "PR_FF") else pES, lag_h)
                    (start_bounds if rel_type in ("PR_FS", "PR_SS") else finish_bounds).append(
                        (t, pred_id, rel_type, lag_h)
                    )
                rs = c.snap_to_work_start(max([dd] + [b[0] for b in start_bounds]))
                start_ties = [b[1:] for b in start_bounds if c.work_hours_between(b[0], rs) <= _TOL]
                finish_floor = max((b[0] for b in finish_bounds), default=None)
                finish_ties = [b[1:] for b in finish_bounds if b[0] == finish_floor]
                act.restart_date = rs

            if act.expect_end_date is not None:
                drtn = max(0.0, c.work_hours_between(rs, act.expect_end_date))
            ef = c.add_work_hours(rs, drtn) if drtn > 0 else rs
            if finish_floor is not None and ef < finish_floor:
                ef = finish_floor
                act.driven_by, act.driving_rels = "logic", finish_ties
            elif start_ties:
                act.driven_by, act.driving_rels = "logic", start_ties
            else:
                act.driven_by = "data_date"
            if cstr["fnet"] and ef < cstr["fnet"]:
                ef = cstr["fnet"]
                act.driven_by, act.driving_rels = "constraint", []
            act.early_end_date = ef
            drtn_of[tid] = drtn
            continue

        # TK_NotStart - initialise ES at data_date.
        es = c.snap_to_work_start(dd)
        driven_by = "data_date"
        bounds: list[tuple[datetime, str, str, float]] = []

        for pred_id, rel_type, lag_h in pred_adj[tid]:
            pred = acts[pred_id]
            p_c = get_cal(pred.clndr_id)  # lag uses predecessor calendar
            pES = pred.early_start_date or dd
            pEF = pred.early_end_date or pES
            if retained_logic and pred.status_code == "TK_Complete":
                # Finished work can't push anything past the data date.
                pES, pEF = min(pES, dd), min(pEF, dd)

            if rel_type == "PR_FS":
                c_date = _bound(p_c, pEF, lag_h)
            elif rel_type == "PR_SS":
                c_date = _bound(p_c, pES, lag_h)
            elif rel_type == "PR_FF":
                c_ef = _bound(p_c, pEF, lag_h)
                c_date = c.sub_work_hours(c_ef, drtn) if drtn > 0 else c_ef
            else:  # PR_SF
                c_ef = _bound(p_c, pES, lag_h)
                c_date = c.sub_work_hours(c_ef, drtn) if drtn > 0 else c_ef

            bounds.append((c_date, pred_id, rel_type, lag_h))
            if c_date > es:
                es = c_date
                driven_by = "logic"

        if cstr["snet"] and cstr["snet"] > es:
            es = cstr["snet"]
            driven_by = "constraint"

        if es < dd:
            es = c.snap_to_work_start(dd)
            driven_by = "data_date"

        es = c.snap_to_work_start(es)

        if cstr["mand_start"]:
            es = c.snap_to_work_start(cstr["mand_start"])
            driven_by = "constraint"

        act.early_start_date = es
        if act.expect_end_date is not None:
            drtn = max(0.0, c.work_hours_between(es, act.expect_end_date))

        if is_milestone or drtn <= 0:
            ef = es
        else:
            ef = c.add_work_hours(es, drtn)

        if cstr["fnet"] and ef < cstr["fnet"]:
            if drtn > 0:
                es_adj = c.sub_work_hours(cstr["fnet"], drtn)
                if es_adj > act.early_start_date:
                    act.early_start_date = c.snap_to_work_start(es_adj)
                ef = c.add_work_hours(act.early_start_date, drtn)
            if ef < cstr["fnet"]:
                ef = cstr["fnet"]
            driven_by = "constraint"

        if cstr["mand_finish"]:
            ef = cstr["mand_finish"]
            act.early_start_date = c.sub_work_hours(ef, drtn) if drtn > 0 else ef
            driven_by = "constraint"

        act.early_end_date = ef
        drtn_of[tid] = drtn
        if driven_by == "logic":
            ties = [b for b in bounds if c.work_hours_between(b[0], act.early_start_date) <= _TOL]
            if retained_logic and ties and all(acts[b[1]].status_code == "TK_Complete" for b in ties):
                driven_by = "data_date"  # a finished predecessor, held at the data date
            else:
                act.driving_rels = [b[1:] for b in ties]
        act.driven_by = driven_by

    # -------------------------------------------------------------------------
    # Project finish date
    # -------------------------------------------------------------------------
    _net_end = max((a.early_end_date for a in acts.values() if a.early_end_date), default=dd)
    proj_end = must_finish_by or _net_end

    # -------------------------------------------------------------------------
    # BACKWARD PASS
    # -------------------------------------------------------------------------
    for tid in reversed(order):
        act = acts[tid]
        c = get_cal(act.clndr_id)
        cstr = _parse_constraints(act)

        if act.status_code == "TK_Complete":
            act.late_start_date = act.early_start_date
            act.late_end_date = act.early_end_date
            continue

        drtn = drtn_of[tid]
        is_milestone = act.task_type in _MILESTONE_TYPES
        lf = proj_end

        for succ_id, rel_type, lag_h in succ_adj[tid]:
            succ = acts[succ_id]
            sLS = succ.late_start_date or proj_end
            sLF = succ.late_end_date or proj_end

            if rel_type == "PR_FS":
                c_date = c.sub_work_hours(sLS, lag_h) if lag_h >= 0 else c.add_work_hours(sLS, -lag_h)
            elif rel_type == "PR_SS":
                net = drtn - lag_h
                c_date = c.add_work_hours(sLS, net) if net >= 0 else c.sub_work_hours(sLS, -net)
            elif rel_type == "PR_FF":
                c_date = c.sub_work_hours(sLF, lag_h) if lag_h >= 0 else c.add_work_hours(sLF, -lag_h)
            else:  # PR_SF
                ls_pred = c.sub_work_hours(sLF, lag_h) if lag_h >= 0 else c.add_work_hours(sLF, -lag_h)
                c_date = c.add_work_hours(ls_pred, drtn) if drtn > 0 else ls_pred

            if c_date < lf:
                lf = c_date

        if cstr["fnlt"] and lf > cstr["fnlt"]:
            lf = cstr["fnlt"]

        act.late_end_date = lf
        act.late_start_date = c.sub_work_hours(lf, drtn) if (drtn > 0 and not is_milestone) else lf

        if cstr["snlt"] and act.late_start_date > cstr["snlt"]:
            act.late_start_date = cstr["snlt"]
            act.late_end_date = c.add_work_hours(act.late_start_date, drtn) if drtn > 0 else act.late_start_date

        if cstr["mand_start"]:
            act.late_start_date = c.snap_to_work_start(cstr["mand_start"])
            act.late_end_date = c.add_work_hours(act.late_start_date, drtn) if drtn > 0 else act.late_start_date
        if cstr["mand_finish"]:
            act.late_end_date = cstr["mand_finish"]
            act.late_start_date = c.sub_work_hours(act.late_end_date, drtn) if drtn > 0 else act.late_end_date

        # Retained Logic: TK_Active LS cannot go before act_start.
        if act.status_code == "TK_Active" and act.act_start_date:
            if act.late_start_date and act.late_start_date < act.act_start_date:
                act.late_start_date = act.act_start_date
            if act.late_end_date and act.early_end_date and act.late_end_date < act.early_end_date:
                act.late_end_date = act.early_end_date

    # -------------------------------------------------------------------------
    # ALAP post-processing
    # -------------------------------------------------------------------------
    for tid in reversed(order):
        act = acts[tid]
        cstr = _parse_constraints(act)
        if cstr["alap"] and act.late_start_date and act.late_end_date:
            act.early_start_date = act.late_start_date
            act.early_end_date = act.late_end_date

    # -------------------------------------------------------------------------
    # FLOAT CALCULATION
    # -------------------------------------------------------------------------
    for act in acts.values():
        if act.status_code == "TK_Complete":
            act.total_float_hr_cnt = 0.0
            act.free_float_hr_cnt = 0.0
            act.tf_days = 0.0
            act.ff_days = 0.0
            continue

        c = get_cal(act.clndr_id)
        hpd = c._cal.hours_per_day if c._cal.hours_per_day > 0 else 8.0

        if retained_logic and act.status_code == "TK_Active" and act.early_end_date and act.late_end_date:
            tf_hr = round(c.work_hours_between(act.early_end_date, act.late_end_date), 4)
            act.total_float_hr_cnt = 0.0 if abs(tf_hr) < 0.01 else tf_hr
            act.tf_days = round(act.total_float_hr_cnt / hpd, 4)
        elif act.early_start_date and act.late_start_date:
            tf_hr = round(c.work_hours_between(act.early_start_date, act.late_start_date), 4)
            if abs(tf_hr) < 0.01:  # guard against -0.001 rounding noise
                tf_hr = 0.0
            act.total_float_hr_cnt = tf_hr
            act.tf_days = round(tf_hr / hpd, 4)
        else:
            act.total_float_hr_cnt = None
            act.tf_days = None

        # Free float = MIN(succ.ES) - EF (minus lag).
        ff = None
        for succ_id, rel_type, lag_h in succ_adj[act.task_id]:
            succ = acts[succ_id]
            succ_start = remaining_start(succ)
            if succ_start and act.early_end_date:
                gap = c.work_hours_between(act.early_end_date, succ_start) - lag_h
                ff = gap if ff is None else min(ff, gap)

        ff_hr = round(ff, 4) if ff is not None else 0.0
        act.free_float_hr_cnt = ff_hr
        act.ff_days = round(ff_hr / hpd, 4)

    # -------------------------------------------------------------------------
    # LONGEST PATH (BFS backward from project end)
    # -------------------------------------------------------------------------
    lp_end = _net_end
    lp_set: set[str] = set()

    seeds = [
        tid
        for tid, act in acts.items()
        if act.early_end_date and abs(get_cal(act.clndr_id).work_hours_between(act.early_end_date, lp_end)) <= _TOL
    ]
    queue: deque[str] = deque(seeds)
    lp_set.update(seeds)

    while queue:
        tid = queue.popleft()
        act = acts[tid]
        c = get_cal(act.clndr_id)

        for pred_id, rel_type, lag_h in pred_adj[tid]:
            pred = acts[pred_id]
            if pred_id in lp_set:
                continue
            pES = pred.early_start_date
            pEF = pred.early_end_date
            aES = remaining_start(act)
            aEF = act.early_end_date

            if rel_type == "PR_FS" and pEF and aES:
                lag_end = c.add_work_hours(pEF, lag_h) if lag_h >= 0 else c.sub_work_hours(pEF, -lag_h)
                rel_ff = c.work_hours_between(lag_end, aES)
            elif rel_type == "PR_SS" and pES and aES:
                lag_end = c.add_work_hours(pES, lag_h) if lag_h >= 0 else c.sub_work_hours(pES, -lag_h)
                rel_ff = c.work_hours_between(lag_end, aES)
            elif rel_type == "PR_FF" and pEF and aEF:
                lag_end = c.add_work_hours(pEF, lag_h) if lag_h >= 0 else c.sub_work_hours(pEF, -lag_h)
                rel_ff = c.work_hours_between(lag_end, aEF)
            elif rel_type == "PR_SF" and pES and aEF:
                lag_end = c.add_work_hours(pES, lag_h) if lag_h >= 0 else c.sub_work_hours(pES, -lag_h)
                rel_ff = c.work_hours_between(lag_end, aEF)
            else:
                continue

            if rel_ff <= _TOL:
                lp_set.add(pred_id)
                queue.append(pred_id)

    for tid, act in acts.items():
        act.lp_critical = tid in lp_set

    critical_tf = sum(1 for a in acts.values() if a.total_float_hr_cnt is not None and a.total_float_hr_cnt <= _TOL)
    logger.info(
        "[CPM] Critical (TF<=0): %d | Longest Path: %d | Project Finish: %s",
        critical_tf,
        len(lp_set),
        lp_end.strftime("%d-%b-%Y") if lp_end else "N/A",
    )

    return parsed
