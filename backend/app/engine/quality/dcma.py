"""DCMA 14-Point Assessment — ported from the reference project's
`backend/app/engine/quality/dcma.py` (416 lines), adapted to run against our
already-loaded SQLAlchemy `Activity`/`ActivityRelationship` rows instead of
the reference's in-memory parsed-snapshot dataclasses. Our `ActivityRelationship`
rows already reference `Activity.id` (our UUID) directly for predecessor/successor
— unlike the reference's `task_id` string joins — so no id-remapping is needed.

Check #10 (Resources) is real when the caller supplies `assigned_activity_ids`
(built from `resource_assignments` rows — see `engine/evm/evm_engine.py` for
the other consumer of that table). Callers that don't pass it get
"not_tracked", excluded from the overall score's denominator (13 applicable
checks instead of 14) rather than counted as an automatic pass or fail —
kept for backward compatibility with any caller that hasn't loaded resource
data.

DCMA 14 checks (reference: DCMA EA PAM 200.1):
  1.  Logic              — open-end activities (no predecessor or no successor)
  2.  Leads               — negative lag relationships
  3.  Lags                — positive lag ratio (>5% = fail)
  4.  Relationship types  — FF+SF relationship ratio (>10% = fail)
  5.  Hard constraints    — Mandatory Start/Finish ratio (>5% = fail)
  6.  High float          — TF > 44 working days ratio (>5% = fail)
  7.  Negative float      — TF < 0 count (any = fail)
  8.  High duration       — remaining duration > 44 working days (>5% = fail)
  9.  Invalid dates       — TK_NotStart with early_start < data_date
  10. Resources           — activities with no resource assignment (>20% = warn)
  11. Missed logic        — TK_Complete with TK_NotStart successors
  12. Critical path length — critical activities vs total (informational)
  13. Total float = 0     — TF=0 but not on the longest path (>10% = warn)
  14. BEI                 — Baseline Execution Index (target: 0.95-1.05)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from app.engine.durations import activity_hours_per_day
from app.models.activity import Activity
from app.models.activity_relationship import ActivityRelationship, LinkType

logger = logging.getLogger(__name__)

_MILESTONE_TYPES = {"TT_Mile", "TT_FinMile", "TT_StartMile"}
# P6's mandatory pair. CS_MSOA / CS_MEOA ("start / finish on or after") used to
# be listed here: they're soft floors, and counting them made nearly every real
# programme fail this check (see engine/cpm/scheduler.py for the same mix-up).
_MAND_CONSTRAINTS = {"CS_MANDSTART", "CS_MANDFIN"}  # Mandatory Start / Finish
_FF_SF_TYPES = {LinkType.FF, LinkType.SF}
_FLOAT_HIGH_DAYS = 44
_DURATION_HIGH_DAYS = 44
_TOL = 0.01


@dataclass
class DcmaCheckResult:
    id: int
    name: str
    status: str  # "pass" | "warn" | "fail" | "not_tracked"
    value: float
    threshold: float
    pct: float
    unit: str  # "count" | "%" | "index"
    details: list[str]  # affected activity external_ids, capped at 20


@dataclass
class DcmaReport:
    computed_at: str
    total_activities: int
    in_scope: int
    overall_score: float
    overall_status: str
    checks: list[DcmaCheckResult]


def _check(
    id: int,
    name: str,
    count: int,
    total: int,
    threshold_pct: float,
    details: list[str],
    unit: str = "%",
    warn_threshold: float | None = None,
) -> DcmaCheckResult:
    pct = round(count / total * 100, 2) if total > 0 else 0.0
    if pct > threshold_pct:
        status = "fail"
    elif warn_threshold is not None and pct > warn_threshold:
        status = "warn"
    else:
        status = "pass"
    return DcmaCheckResult(
        id=id, name=name, status=status, value=float(count), threshold=threshold_pct,
        pct=pct, unit=unit, details=details[:20],
    )


def _check1_logic(acts: list[Activity], rels: list[ActivityRelationship], total: int) -> DcmaCheckResult:
    act_ids = {a.id for a in acts}
    has_pred: set = set()
    has_succ: set = set()
    for r in rels:
        if r.predecessor_id in act_ids:
            has_succ.add(r.predecessor_id)
        if r.successor_id in act_ids:
            has_pred.add(r.successor_id)

    open_ends = [
        a for a in acts
        if a.task_type not in _MILESTONE_TYPES and (a.id not in has_pred or a.id not in has_succ)
    ]
    return _check(1, "Logic (Open Ends)", len(open_ends), total, 5.0, [a.external_id for a in open_ends])


def _check2_leads(rels: list[ActivityRelationship], id_to_code: dict, total: int) -> DcmaCheckResult:
    leads = [r for r in rels if (r.lag_hours or 0) < 0]
    codes = [id_to_code.get(r.predecessor_id, "") for r in leads]
    return _check(2, "Leads (Negative Lag)", len(leads), total, 0.0, codes)


def _check3_lags(rels: list[ActivityRelationship], id_to_code: dict, total: int) -> DcmaCheckResult:
    lags = [r for r in rels if (r.lag_hours or 0) > 0]
    pct = round(len(lags) / len(rels) * 100, 2) if rels else 0.0
    status = "fail" if pct > 5.0 else "pass"
    codes = [id_to_code.get(r.predecessor_id, "") for r in lags[:20]]
    return DcmaCheckResult(
        id=3, name="Lags (Positive Lag)", status=status, value=float(len(lags)), threshold=5.0,
        pct=pct, unit="%", details=codes,
    )


def _check4_rel_types(rels: list[ActivityRelationship], id_to_code: dict, total: int) -> DcmaCheckResult:
    ff_sf = [r for r in rels if r.link_type in _FF_SF_TYPES]
    pct = round(len(ff_sf) / len(rels) * 100, 2) if rels else 0.0
    status = "fail" if pct > 10.0 else ("warn" if pct > 5.0 else "pass")
    codes = [id_to_code.get(r.predecessor_id, "") for r in ff_sf[:20]]
    return DcmaCheckResult(
        id=4, name="Relationship Types (FF+SF)", status=status, value=float(len(ff_sf)), threshold=10.0,
        pct=pct, unit="%", details=codes,
    )


def _check5_hard_constraints(acts: list[Activity], total: int) -> DcmaCheckResult:
    hard = [
        a for a in acts
        if (a.constraint_type in _MAND_CONSTRAINTS) or (a.constraint_type_2 in _MAND_CONSTRAINTS)
    ]
    return _check(5, "Hard Constraints (Mandatory)", len(hard), total, 5.0, [a.external_id for a in hard])


def _check6_high_float(acts: list[Activity], hpd: float, total: int) -> DcmaCheckResult:
    # 44 working days on each activity's OWN calendar (engine/durations.py);
    # `hpd` is only the fallback for one with no calendar.
    high = [
        a for a in acts
        if a.total_float_hours is not None and a.total_float_hours > _FLOAT_HIGH_DAYS * activity_hours_per_day(a, hpd)
    ]
    return _check(6, f"High Float (TF > {_FLOAT_HIGH_DAYS}d)", len(high), total, 5.0, [a.external_id for a in high])


def _check7_negative_float(acts: list[Activity], total: int) -> DcmaCheckResult:
    neg = [a for a in acts if a.total_float_hours is not None and a.total_float_hours < -_TOL]
    return _check(7, "Negative Float", len(neg), total, 0.0, [a.external_id for a in neg])


def _check8_high_duration(acts: list[Activity], hpd: float, total: int) -> DcmaCheckResult:
    high = [
        a for a in acts
        if (a.remaining_duration_hours or 0) > _DURATION_HIGH_DAYS * activity_hours_per_day(a, hpd)
        and a.status_code != "TK_Complete"
        and a.task_type not in _MILESTONE_TYPES
    ]
    return _check(
        8, f"High Duration (RD > {_DURATION_HIGH_DAYS}d)", len(high), total, 5.0, [a.external_id for a in high]
    )


def _check9_invalid_dates(acts: list[Activity], data_date: date, total: int) -> DcmaCheckResult:
    invalid = [
        a for a in acts
        if a.status_code == "TK_NotStart" and a.early_start is not None and a.early_start < data_date
    ]
    return _check(9, "Invalid Dates (ES < Data Date)", len(invalid), total, 0.0, [a.external_id for a in invalid])


def _check10_resources(
    acts: list[Activity], assigned_activity_ids: Optional[set[uuid.UUID]], total: int
) -> DcmaCheckResult:
    if assigned_activity_ids is None:
        return DcmaCheckResult(
            id=10, name="Resources (Unassigned)", status="not_tracked", value=0.0, threshold=20.0,
            pct=0.0, unit="%", details=[],
        )
    no_rsrc = [
        a for a in acts
        if a.id not in assigned_activity_ids and a.task_type not in _MILESTONE_TYPES and a.status_code != "TK_Complete"
    ]
    codes = [a.external_id for a in no_rsrc]
    pct = round(len(no_rsrc) / total * 100, 2) if total > 0 else 0.0
    status = "warn" if pct > 20.0 else "pass"
    return DcmaCheckResult(
        id=10, name="Resources (Unassigned)", status=status, value=float(len(no_rsrc)), threshold=20.0,
        pct=pct, unit="%", details=codes[:20],
    )


def _check11_missed_logic(
    acts: list[Activity], rels: list[ActivityRelationship], id_to_code: dict, total: int
) -> DcmaCheckResult:
    status_map = {a.id: a.status_code for a in acts}
    complete_ids = {a.id for a in acts if a.status_code == "TK_Complete"}
    missed = set()
    for r in rels:
        if r.predecessor_id in complete_ids and status_map.get(r.successor_id) == "TK_NotStart":
            missed.add(r.predecessor_id)
    codes = [id_to_code.get(aid, "") for aid in list(missed)[:20]]
    return _check(11, "Missed Logic (Complete→NotStart)", len(missed), total, 5.0, codes)


def _check12_critical_path_length(acts: list[Activity], total: int) -> DcmaCheckResult:
    critical = [
        a for a in acts
        if a.total_float_hours is not None and abs(a.total_float_hours) <= _TOL
        and a.status_code != "TK_Complete"
    ]
    pct = round(len(critical) / total * 100, 2) if total > 0 else 0.0
    status = "warn" if (pct < 5.0 or pct > 20.0) else "pass"
    return DcmaCheckResult(
        id=12, name="Critical Path Length", status=status, value=float(len(critical)), threshold=20.0,
        pct=pct, unit="%", details=[a.external_id for a in critical[:20]],
    )


def _check13_total_float_zero(acts: list[Activity], total: int) -> DcmaCheckResult:
    zero_float = [
        a for a in acts
        if a.total_float_hours is not None and abs(a.total_float_hours) <= _TOL
        and not a.is_longest_path
        and a.status_code != "TK_Complete"
    ]
    pct = round(len(zero_float) / total * 100, 2) if total > 0 else 0.0
    status = "warn" if pct > 10.0 else "pass"
    return DcmaCheckResult(
        id=13, name="Total Float = 0 (Artificial)", status=status, value=float(len(zero_float)), threshold=10.0,
        pct=pct, unit="%", details=[a.external_id for a in zero_float[:20]],
    )


def _check14_bei(acts: list[Activity], data_date: date) -> DcmaCheckResult:
    planned_done = [a for a in acts if a.planned_finish and a.planned_finish <= data_date]
    actually_done = [
        a for a in planned_done
        if a.status_code == "TK_Complete" and a.actual_finish and a.actual_finish <= data_date
    ]
    expected = len(planned_done)
    completed = len(actually_done)

    if expected == 0:
        bei = 1.0
        status = "pass"
    else:
        bei = round(completed / expected, 4)
        if 0.95 <= bei <= 1.05:
            status = "pass"
        elif 0.85 <= bei <= 1.15:
            status = "warn"
        else:
            status = "fail"

    missed_codes = [a.external_id for a in planned_done if a.status_code != "TK_Complete"][:20]
    return DcmaCheckResult(
        id=14, name="BEI (Baseline Execution Index)", status=status, value=bei, threshold=0.95,
        pct=round(bei * 100, 2), unit="index", details=missed_codes,
    )


def run_dcma(
    activities: list[Activity],
    relationships: list[ActivityRelationship],
    hours_per_day: float,
    data_date: datetime | None,
    assigned_activity_ids: Optional[set[uuid.UUID]] = None,
) -> DcmaReport:
    """Run all 14 DCMA checks against a project's current activities/relationships.
    `assigned_activity_ids` (activity ids with >=1 resource_assignments row) makes
    check #10 real instead of "not_tracked" — see module docstring."""
    dd = (data_date or datetime.utcnow()).date()
    hpd = hours_per_day if hours_per_day > 0 else 8.0

    in_scope = [a for a in activities if a.status_code != "TK_Complete" and a.task_type != "TT_WBS"]
    total = max(len(in_scope), 1)
    id_to_code = {a.id: a.external_id for a in activities}

    checks: list[DcmaCheckResult] = [
        _check1_logic(in_scope, relationships, total),
        _check2_leads(relationships, id_to_code, total),
        _check3_lags(relationships, id_to_code, total),
        _check4_rel_types(relationships, id_to_code, total),
        _check5_hard_constraints(in_scope, total),
        _check6_high_float(in_scope, hpd, total),
        _check7_negative_float(in_scope, total),
        _check8_high_duration(in_scope, hpd, total),
        _check9_invalid_dates(in_scope, dd, total),
        _check10_resources(in_scope, assigned_activity_ids, total),
        _check11_missed_logic(activities, relationships, id_to_code, total),
        _check12_critical_path_length(in_scope, total),
        _check13_total_float_zero(in_scope, total),
        _check14_bei(activities, dd),
    ]

    applicable = [c for c in checks if c.status != "not_tracked"]
    pass_pts = sum(1 for c in applicable if c.status == "pass")
    warn_pts = sum(1 for c in applicable if c.status == "warn")
    score = round((pass_pts * 1.0 + warn_pts * 0.5) / len(applicable) * 100, 1) if applicable else 0.0

    fail_count = sum(1 for c in applicable if c.status == "fail")
    warn_count = sum(1 for c in applicable if c.status == "warn")
    overall = "fail" if fail_count > 0 else ("warn" if warn_count > 0 else "pass")

    logger.info(
        "[DCMA] Score=%.1f Pass=%d Warn=%d Fail=%d (in-scope=%d)",
        score, pass_pts, warn_count, fail_count, len(in_scope),
    )

    return DcmaReport(
        computed_at=datetime.utcnow().isoformat(),
        total_activities=len(activities),
        in_scope=len(in_scope),
        overall_score=score,
        overall_status=overall,
        checks=checks,
    )
