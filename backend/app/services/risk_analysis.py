"""QSRA orchestration: register -> engine -> persisted, explainable results.

Method and defaults follow AACE RP 57R-09 / Hulett's risk-driver approach (see
engine/risk/qsra.py). What this module adds on top of the engine:

  - the uncertainty POLICY (which activities get which background range);
  - turning register risks into drivers, with the guards that stop double
    counting (closed risks, impacts already in the P6 schedule) and the
    warnings that stop common modelling mistakes (a delay risk linked to
    activities in sequence adds its delay once per activity);
  - calibration: the simulation with every factor at 1 and no risks must land
    on the CPM finish, or its results are flagged — never silently shifted;
  - three runs on common random numbers — pre-mitigation, post-mitigation and
    background only — which is what the waterfall and "mitigation benefit"
    compare;
  - outputs in working days and calendar dates, and the rule-based
    recommendations that read them.
"""

from __future__ import annotations

import bisect
import time as _time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import date, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.engine.risk.qsra import (
    CorrelationWeights,
    RiskDriver,
    SimulationResult,
    percentile,
    rank_risks,
    simulate,
)
from app.models.activity import Activity
from app.models.baseline import Baseline, BaselineStatus
from app.models.risk_analysis import RiskAnalysisSettings, RiskSimulationRun
from app.models.risk_item import RiskItem, RiskStatus
from app.services.risk_network import MILESTONE_TYPES, ScheduleNetwork, build_network
from app.services.schedule_current import get_current_import

# Background ranges (min / most likely / max factors on remaining duration).
# Starting points, not a standard — Hulett's example range is the "high"
# confidence one; see the research brief behind this module.
CONFIDENCE_RANGES: dict[str, tuple[float, float, float]] = {
    "high": (0.95, 1.00, 1.10),
    "medium": (0.90, 1.00, 1.20),
    "low": (0.90, 1.05, 1.40),
}
CONFIDENCE_LABELS = {
    "high": "High — repetitive work, stable productivity",
    "medium": "Medium — typical building / EPC construction",
    "low": "Low — design-led, first-of-a-kind, commissioning, approvals",
}
# Activities whose names carry these words get the low-confidence range
# whatever the project level: their durations are the least predictable.
LOW_CONFIDENCE_KEYWORDS = ("commission", "testing", "test ", "permit", "approval", "design", "authority", "inspection")
_LONG_DURATION_DAYS = 44  # DCMA high-duration threshold, in working days

# 1–5 register score -> probability %, when a risk hasn't been given one.
SCORE_TO_PCT = {1: 5.0, 2: 20.0, 3: 40.0, 4: 60.0, 5: 85.0}

_MAX_WORK_UNITS = 4_000_000  # iterations x network size before iterations are capped
_CDF_POINTS = 60


def pct_to_score(pct: float) -> int:
    if pct < 10:
        return 1
    if pct < 30:
        return 2
    if pct < 50:
        return 3
    if pct < 70:
        return 4
    return 5


def get_settings(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> RiskAnalysisSettings:
    row = (
        db.query(RiskAnalysisSettings)
        .filter(RiskAnalysisSettings.tenant_id == tenant_id, RiskAnalysisSettings.project_id == project_id)
        .first()
    )
    if row is None:
        row = RiskAnalysisSettings(
            id=uuid.uuid4(), tenant_id=tenant_id, project_id=project_id, confidence="medium",
            iterations=1000, seed=20260929, near_critical_days=10.0, correlate_by_wbs=True,
        )
        db.add(row)
        db.flush()
    return row


def baseline_finish(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> Optional[date]:
    b = (
        db.query(Baseline)
        .filter(Baseline.tenant_id == tenant_id, Baseline.project_id == project_id, Baseline.status == BaselineStatus.active)
        .first()
    )
    return b.target_end_date if b else None


def background_policy(level: str):
    project_range = CONFIDENCE_RANGES.get(level, CONFIDENCE_RANGES["medium"])
    low_range = CONFIDENCE_RANGES["low"]

    def background_for(a: Activity, hpd: float) -> tuple[float, float, float]:
        if (a.task_type or "") in MILESTONE_TYPES:
            return (1.0, 1.0, 1.0)
        remaining = a.remaining_duration_hours if a.remaining_duration_hours is not None else (a.remaining_duration_days or 0) * hpd
        if remaining <= hpd:  # a day or less left: nothing meaningful to range
            return (1.0, 1.0, 1.0)
        original_days = (a.target_duration_hours or 0.0) / (hpd or 8.0)
        name = f" {(a.name or '').lower()} "
        if original_days > _LONG_DURATION_DAYS or any(k in name for k in LOW_CONFIDENCE_KEYWORDS):
            return low_range
        return project_range

    return background_for


@dataclass
class DriverBuild:
    pre: list[RiskDriver]
    post: list[RiskDriver]
    meta: list[dict]
    no_effect: list[dict]
    warnings: list[str]
    derived_probability: list[str]
    has_post: bool


def _reachable(sn: ScheduleNetwork, start: set[int], targets: set[int]) -> bool:
    """Is any of `targets` reachable downstream from another member of the set?"""
    succ: dict[int, list[int]] = {}
    for i, preds in enumerate(sn.network.preds):
        for p, _k, _l in preds:
            succ.setdefault(p, []).append(i)
    for s in start:
        seen = {s}
        queue = deque(succ.get(s, []))
        while queue:
            x = queue.popleft()
            if x in seen:
                continue
            if x in targets and x != s:
                return True
            seen.add(x)
            queue.extend(succ.get(x, []))
    return False


def build_drivers(risks: list[RiskItem], sn: ScheduleNetwork) -> DriverBuild:
    pre: list[RiskDriver] = []
    post: list[RiskDriver] = []
    meta: list[dict] = []
    no_effect: list[dict] = []
    warnings: list[str] = []
    derived: list[str] = []
    has_post = False

    for r in sorted(risks, key=lambda x: x.code):
        if not r.qsra_enabled:
            continue
        if r.status == RiskStatus.closed:
            continue
        if r.impact_in_schedule:
            no_effect.append({"code": r.code, "title": r.title, "reason": "Impact already in the P6 schedule"})
            continue
        if r.impact_ml is None and r.impact_max is None:
            no_effect.append({"code": r.code, "title": r.title, "reason": "No impact range entered"})
            continue

        if r.apply_to_wbs and r.wbs_path:
            wbs_ids = sn.descendants_by_wbs.get(r.wbs_path, {r.wbs_path})
            idx = [i for i, a in enumerate(sn.activities) if a.wbs_path in wbs_ids]
        else:
            idx = [sn.index_by_external_id[e] for e in (r.activity_external_ids or []) if e in sn.index_by_external_id]
        idx = [i for i in idx if sn.network.activities[i].status != "complete"]
        if not idx:
            no_effect.append({"code": r.code, "title": r.title, "reason": "Linked only to completed or missing activities"})
            continue

        if r.probability_pct is None:
            prob = SCORE_TO_PCT.get(r.probability, 40.0)
            derived.append(r.code)
        else:
            prob = r.probability_pct
        if r.status == RiskStatus.occurred:
            prob = 100.0

        lo = r.impact_min if r.impact_min is not None else (r.impact_ml or 0.0)
        ml = r.impact_ml if r.impact_ml is not None else (lo + (r.impact_max or lo)) / 2.0
        hi = r.impact_max if r.impact_max is not None else ml
        lo, ml, hi = max(0.0, lo), max(0.0, ml), max(0.0, hi)
        lo, hi = min(lo, hi), max(lo, hi)
        ml = min(max(ml, lo), hi)

        post_prob = r.post_probability_pct if r.post_probability_pct is not None else prob
        if r.status == RiskStatus.occurred:
            post_prob = 100.0
        p_lo = r.post_impact_min if r.post_impact_min is not None else lo
        p_ml = r.post_impact_ml if r.post_impact_ml is not None else ml
        p_hi = r.post_impact_max if r.post_impact_max is not None else hi
        p_lo, p_hi = min(p_lo, p_hi), max(p_lo, p_hi)
        p_ml = min(max(p_ml, p_lo), p_hi)
        if (post_prob, p_lo, p_ml, p_hi) != (prob, lo, ml, hi):
            has_post = True

        opp = r.risk_kind == "opportunity"
        mode = r.impact_mode if r.impact_mode in ("duration_pct", "delay_days") else "duration_pct"
        dist = r.impact_distribution if r.impact_distribution in ("triangular", "pert", "uniform") else "triangular"
        pre.append(RiskDriver(r.code, r.title, prob / 100.0, (lo, ml, hi), dist, mode, idx, opp))
        post.append(RiskDriver(r.code, r.title, post_prob / 100.0, (p_lo, p_ml, p_hi), dist, mode, idx, opp))

        if mode == "delay_days" and len(idx) > 1 and _reachable(sn, set(idx), set(idx)):
            warnings.append(
                f"{r.code}: this delay risk is linked to activities in sequence, so its delay is added once per "
                f"activity. Link a delay risk to the activity where the delay first bites."
            )

        meta.append(
            {
                "code": r.code,
                "title": r.title,
                "owner": r.owner_name,
                "kind": r.risk_kind,
                "mode": mode,
                "distribution": dist,
                "probability_pct": round(prob, 1),
                "impact": [round(lo, 2), round(ml, 2), round(hi, 2)],
                "post_probability_pct": round(post_prob, 1),
                "post_impact": [round(p_lo, 2), round(p_ml, 2), round(p_hi, 2)],
                "activity_count": len(idx),
                "status": r.status.value,
                "mitigation_status": r.mitigation_status.value,
                "probability_derived": r.probability_pct is None,
            }
        )
    return DriverBuild(pre, post, meta, no_effect, warnings, derived, has_post)


def _summary(sn: ScheduleNetwork, res: SimulationResult, cpm_offset: float, target_offset: Optional[float]) -> dict:
    offs = res.offsets_sorted
    n = len(offs)

    def d(off: float) -> str:
        return sn.offset_to_date(off).isoformat()

    def days(h: float) -> float:
        return round(sn.hours_to_days(h), 1)

    p = {k: percentile(offs, v) for k, v in (("p10", 10), ("p50", 50), ("p80", 80), ("p90", 90))}
    out = {
        "p10": d(p["p10"]), "p50": d(p["p50"]), "p80": d(p["p80"]), "p90": d(p["p90"]),
        "p10_days": days(p["p10"] - cpm_offset), "p50_days": days(p["p50"] - cpm_offset),
        "p80_days": days(p["p80"] - cpm_offset), "p90_days": days(p["p90"] - cpm_offset),
        "min": d(offs[0]), "max": d(offs[-1]),
        "mean": d(res.mean_offset), "sd_days": days(res.sd_offset),
        "prob_meet_cpm": round(100.0 * sum(1 for o in offs if o <= cpm_offset + 0.5) / n, 1),
        "prob_meet_target": (
            round(100.0 * sum(1 for o in offs if o <= target_offset + 0.5) / n, 1) if target_offset is not None else None
        ),
        "contingency_p80_days": days(max(0.0, p["p80"] - cpm_offset)),
    }
    # CDF sampled at evenly spaced working-hour offsets.
    lo, hi = offs[0], offs[-1]
    cdf = []
    if hi <= lo:
        cdf = [{"date": d(lo), "pct": 100.0}]
    else:
        for k in range(_CDF_POINTS + 1):
            x = lo + (hi - lo) * k / _CDF_POINTS
            cdf.append({"date": d(x), "pct": round(100.0 * bisect.bisect_right(offs, x) / n, 1)})
    out["cdf"] = cdf
    # Histogram: a working day per bin if the range is short, else a week.
    span_days = sn.hours_to_days(hi - lo)
    bin_h = sn.hours_per_day * (1 if span_days <= 60 else 5)
    bins = []
    if hi > lo:
        start = lo
        while start <= hi and len(bins) < 200:
            end = start + bin_h
            count = sum(1 for o in offs if start <= o < end) if end <= hi else sum(1 for o in offs if o >= start)
            bins.append({"date": d(start), "count": count})
            start = end
    else:
        bins = [{"date": d(lo), "count": n}]
    out["histogram"] = bins
    out["bin"] = "day" if span_days <= 60 else "week"
    return out


def run_qsra(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID, user_id: Optional[uuid.UUID]) -> RiskSimulationRun:
    started = _time.perf_counter()
    settings = get_settings(db, tenant_id, project_id)
    sn = build_network(
        db, tenant_id, project_id, background_policy(settings.confidence), correlate_by_wbs=settings.correlate_by_wbs
    )
    if not sn.activities:
        raise ValueError("This project has no activities yet — import a schedule first.")
    if all(a.status == "complete" for a in sn.network.activities):
        raise ValueError("Every activity is complete — there is no remaining work to simulate.")

    risks = db.query(RiskItem).filter(RiskItem.tenant_id == tenant_id, RiskItem.project_id == project_id).all()
    built = build_drivers(risks, sn)

    target_idx = None
    finish_act = settings.finish_activity_external_id
    if finish_act and finish_act in sn.index_by_external_id:
        target_idx = sn.index_by_external_id[finish_act]

    # CPM finish: the P6 / Poko early finish of the measured activity.
    remaining_acts = [a for a in sn.activities if a.early_finish or a.actual_finish]
    if target_idx is not None:
        a = sn.activities[target_idx]
        cpm_date = a.early_finish or a.actual_finish
    else:
        cpm_date = max((a.early_finish or a.actual_finish for a in remaining_acts), default=None)
    cpm_offset = sn.date_to_offset(cpm_date) if cpm_date else None

    target = settings.target_date or baseline_finish(db, tenant_id, project_id)
    target_offset = sn.date_to_offset(target) if target else None

    size = sn.network.n + sum(len(p) for p in sn.network.preds)
    iterations = max(200, min(settings.iterations, _MAX_WORK_UNITS // max(1, size)))
    weights = CorrelationWeights()
    hpd = sn.hours_per_day

    pre = simulate(sn.network, built.pre, iterations=iterations, hours_per_day=hpd, seed=settings.seed,
                   weights=weights, target_index=target_idx)
    background = simulate(
        sn.network,
        [RiskDriver(d.key, d.title, 0.0, d.impact, d.distribution, d.mode, d.activity_indices, d.is_opportunity) for d in built.pre],
        iterations=iterations, hours_per_day=hpd, seed=settings.seed, weights=weights,
        target_index=target_idx, track_activities=False,
    )
    post = (
        simulate(sn.network, built.post, iterations=iterations, hours_per_day=hpd, seed=settings.seed,
                 weights=weights, target_index=target_idx, track_activities=False)
        if built.has_post else None
    )

    if cpm_offset is None:
        cpm_offset = pre.calibration_offset
        cpm_date = sn.offset_to_date(cpm_offset)
    calibration_delta_days = round(sn.hours_to_days(pre.calibration_offset - cpm_offset), 1)
    remaining_days = max(1.0, sn.hours_to_days(cpm_offset))
    calibration_ok = abs(calibration_delta_days) <= max(5.0, 0.02 * remaining_days)

    pre_summary = _summary(sn, pre, cpm_offset, target_offset)
    bg_summary = _summary(sn, background, cpm_offset, target_offset)
    post_summary = _summary(sn, post, cpm_offset, target_offset) if post else None

    def p80(res: SimulationResult) -> float:
        return percentile(res.offsets_sorted, 80)

    waterfall = [
        {"label": "CPM finish", "date": cpm_date.isoformat(), "delta_days": 0.0},
        {"label": "+ Background uncertainty (P80)", "date": bg_summary["p80"],
         "delta_days": round(sn.hours_to_days(p80(background) - cpm_offset), 1)},
        {"label": "+ Risk events (P80)", "date": pre_summary["p80"],
         "delta_days": round(sn.hours_to_days(p80(pre) - p80(background)), 1)},
    ]
    if post:
        waterfall.append({"label": "− Mitigation (P80)", "date": post_summary["p80"],
                          "delta_days": round(sn.hours_to_days(p80(post) - p80(pre)), 1)})

    meta_by_code = {m["code"]: m for m in built.meta}
    driver_rows = []
    for s in pre.drivers:
        m = meta_by_code.get(s.key, {})
        driver_rows.append({
            **m,
            "occurred_pct": s.occurred_pct,
            "delay_when_occurs_days": s.delay_when_occurs_days,
            "expected_delay_days": s.expected_delay_days,
            "critical_hit_pct": s.critical_hit_pct,
        })

    near_days = settings.near_critical_days
    act_rows = []
    for st in pre.activities:
        a = sn.activities[st.index]
        sim_a = sn.network.activities[st.index]
        if sim_a.status == "complete":
            continue
        tf_days = round((a.total_float_hours or 0.0) / hpd, 1) if a.total_float_hours is not None else None
        act_rows.append({
            "external_id": a.external_id,
            "name": a.name,
            "wbs_path": a.wbs_path,
            "criticality_pct": st.criticality_pct,
            "ssi": st.ssi,
            "cruciality": st.cruciality,
            "sd_days": round(st.duration_sd_hours / hpd, 1),
            "total_float_days": tf_days,
            "p6_critical": bool(a.is_critical),
            "hidden_driver": st.criticality_pct >= 40 and tf_days is not None and tf_days > near_days,
        })
    act_rows.sort(key=lambda r: (r["ssi"], r["criticality_pct"]), reverse=True)

    model_check = {
        "calibration_finish": sn.offset_to_date(pre.calibration_offset).isoformat(),
        "calibration_delta_days": calibration_delta_days,
        "calibration_ok": calibration_ok,
        "hard_constraints": sn.hard_constraint_ids[:50],
        "hard_constraint_count": len(sn.hard_constraint_ids),
        "open_end_count": len(sn.open_end_ids),
        "open_ends": sn.open_end_ids[:50],
        "summary_excluded": sn.summary_count,
        "no_effect": built.no_effect,
        "warnings": built.warnings,
        "derived_probability": built.derived_probability,
        "network_size": sn.network.n,
        "uncertain_activities": len(sn.network.uncertain),
        "groups": len(sn.group_names),
        "iterations_capped": iterations < settings.iterations,
    }

    results = {
        "cpm_finish": cpm_date.isoformat(),
        "target_date": target.isoformat() if target else None,
        "target_source": "settings" if settings.target_date else ("baseline" if target else None),
        "measured": (
            {"external_id": finish_act, "name": sn.activities[target_idx].name}
            if target_idx is not None else None
        ),
        "pre": pre_summary,
        "post": post_summary,
        "background": {k: bg_summary[k] for k in ("p10", "p50", "p80", "p90", "p80_days")},
        "mitigation_benefit_p80_days": (
            round(sn.hours_to_days(p80(pre) - p80(post)), 1) if post else None
        ),
        "risk_exposure_p80_days": round(sn.hours_to_days(p80(pre) - p80(background)), 1),
        "waterfall": waterfall,
        "drivers": driver_rows,
        "activities": act_rows[:40],
        "hidden_drivers": [r for r in act_rows if r["hidden_driver"]][:20],
        "model_check": model_check,
        "confidence": settings.confidence,
    }
    results["recommendations"] = qsra_recommendations(results)

    current = get_current_import(db, tenant_id, project_id)
    run = RiskSimulationRun(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        project_id=project_id,
        schedule_import_id=current.id if current else None,
        revision_label=(current.revision_label or current.filename) if current else None,
        data_date=sn.data_date.replace(tzinfo=timezone.utc),
        iterations=iterations,
        seed=settings.seed,
        duration_ms=int((_time.perf_counter() - started) * 1000),
        settings={
            "confidence": settings.confidence,
            "iterations": settings.iterations,
            "target_date": settings.target_date.isoformat() if settings.target_date else None,
            "finish_activity_external_id": settings.finish_activity_external_id,
            "near_critical_days": settings.near_critical_days,
            "correlate_by_wbs": settings.correlate_by_wbs,
        },
        inputs={"risks": built.meta},
        results=results,
        created_by_user_id=user_id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def run_ranking(db: Session, run: RiskSimulationRun, tenant_id: uuid.UUID, project_id: uuid.UUID) -> RiskSimulationRun:
    """Full Hulett ranking for the latest schedule: each risk switched off in
    turn, on common random numbers. Capped to the 15 risks the screening ranks
    highest — the rest can't move P80 materially."""
    settings = get_settings(db, tenant_id, project_id)
    sn = build_network(db, tenant_id, project_id, background_policy(settings.confidence),
                       correlate_by_wbs=settings.correlate_by_wbs)
    risks = db.query(RiskItem).filter(RiskItem.tenant_id == tenant_id, RiskItem.project_id == project_id).all()
    built = build_drivers(risks, sn)
    if not built.pre:
        raise ValueError("No quantified risks to rank — quantify at least one risk in the register.")
    screening = {r["code"]: abs(r.get("expected_delay_days") or 0) for r in (run.results or {}).get("drivers", [])}
    drivers = sorted(built.pre, key=lambda d: screening.get(d.key, 0), reverse=True)[:15]
    target_idx = sn.index_by_external_id.get(settings.finish_activity_external_id or "")
    size = sn.network.n + sum(len(p) for p in sn.network.preds)
    iterations = max(200, min(500, settings.iterations, _MAX_WORK_UNITS // max(1, size)))
    p_all, p_bg, ranking = rank_risks(
        sn.network, drivers, iterations=iterations, hours_per_day=sn.hours_per_day, seed=settings.seed,
        target_index=target_idx,
    )
    exposure = sn.hours_to_days(p_all - p_bg)
    titles = {d.key: d.title for d in drivers}
    run.ranking = [
        {
            "code": key,
            "title": titles.get(key, ""),
            "delta_p80_days": dp80,
            "delta_p50_days": dp50,
            "share_pct": round(100.0 * dp80 / exposure, 1) if exposure > 0 else None,
        }
        for key, dp80, dp50 in ranking
    ]
    results = dict(run.results or {})
    results["ranking_meta"] = {"iterations": iterations, "exposure_p80_days": round(exposure, 1)}
    results["recommendations"] = qsra_recommendations(results, run.ranking)
    run.results = results
    db.commit()
    db.refresh(run)
    return run


# --- recommendations ---------------------------------------------------------------


def _fmt(d: Optional[str]) -> str:
    if not d:
        return "—"
    x = date.fromisoformat(d)
    return x.strftime("%d-%b-%Y")


def qsra_recommendations(results: dict, ranking: Optional[list] = None) -> list[dict]:
    """Rules read the stored results only, so they can be re-derived later."""
    out: list[dict] = []
    pre = results.get("pre") or {}
    exposure = results.get("risk_exposure_p80_days") or 0.0

    p_cpm = pre.get("prob_meet_cpm")
    if p_cpm is not None and p_cpm < 30:
        out.append({
            "id": "cpm-not-credible", "severity": "red", "area": "Confidence",
            "message": (
                f"The current CPM finish ({_fmt(results.get('cpm_finish'))}) has a {p_cpm:.0f}% probability of "
                f"being met. Committing to {_fmt(pre.get('p80'))} (P80) needs {pre.get('contingency_p80_days', 0):.0f} "
                f"working days of schedule contingency."
            ),
            "link": "/risk",
        })

    p_target = pre.get("prob_meet_target")
    if p_target is not None and p_target < 10 and results.get("target_date"):
        top = ", ".join(a["external_id"] for a in (results.get("activities") or [])[:3])
        out.append({
            "id": "target-unlikely", "severity": "red", "area": "Confidence",
            "message": (
                f"Meeting {_fmt(results['target_date'])} is unlikely ({p_target:.0f}%). The activities with the "
                f"highest schedule sensitivity are {top or '—'} — recovery effort there moves the finish most."
            ),
            "link": "/risk",
        })

    rank_rows = ranking or []
    by_code = {d["code"]: d for d in results.get("drivers") or []}
    for row in rank_rows[:3]:
        share = row.get("share_pct")
        if row["delta_p80_days"] >= 10 or (share is not None and share >= 25):
            d = by_code.get(row["code"], {})
            out.append({
                "id": f"dominant-{row['code']}", "severity": "amber", "area": "Risk",
                "message": (
                    f"Risk {row['code']} '{row['title']}' drives "
                    + (f"{share:.0f}% of the risk exposure at P80. " if share is not None else "the P80 finish. ")
                    + f"Mitigating it could recover about {row['delta_p80_days']:.0f} working days at P80."
                    + (f" Owner: {d['owner']}." if d.get("owner") else "")
                ),
                "link": "/risk/register",
            })
    for d in results.get("drivers") or []:
        impact = d.get("expected_delay_days") or 0
        if impact >= 5 and d.get("mitigation_status") in ("none", "draft") and d.get("kind") != "opportunity":
            out.append({
                "id": f"unmitigated-{d['code']}", "severity": "amber", "area": "Risk",
                "message": (
                    f"Risk {d['code']} adds about {impact:.0f} working days to the expected finish and has no "
                    f"accepted mitigation plan."
                ),
                "link": "/risk/mitigation-plans",
            })
    benefit = results.get("mitigation_benefit_p80_days")
    if benefit is not None and exposure > 0 and benefit < 0.2 * exposure:
        out.append({
            "id": "weak-mitigation", "severity": "amber", "area": "Risk",
            "message": (
                f"The mitigation plans recover {benefit:.0f} of {exposure:.0f} working days of risk exposure at P80. "
                f"Consider avoiding or transferring the largest risks instead."
            ),
            "link": "/risk/mitigation-plans",
        })
    for a in (results.get("hidden_drivers") or [])[:3]:
        out.append({
            "id": f"hidden-{a['external_id']}", "severity": "amber", "area": "Criticality",
            "message": (
                f"{a['external_id']} — {a['name']} has {a['total_float_days']:.0f} days of float in the schedule but "
                f"drives the finish in {a['criticality_pct']:.0f}% of simulations. Manage it as critical."
            ),
            "link": "/risk",
        })
    mc = results.get("model_check") or {}
    if mc and not mc.get("calibration_ok", True):
        out.append({
            "id": "calibration", "severity": "amber", "area": "Model",
            "message": (
                f"The simulation model doesn't reproduce the CPM finish (Δ {mc['calibration_delta_days']:+.0f} working "
                f"days) — results may be biased. Likely causes: mixed calendars, constraints, or out-of-sequence progress."
            ),
            "link": "/risk",
        })
    if mc.get("hard_constraint_count"):
        out.append({
            "id": "hard-constraints", "severity": "info", "area": "Model",
            "message": (
                f"{mc['hard_constraint_count']} activities carry mandatory constraints. They're treated as floors only; "
                f"a mandatory date can't absorb uncertainty, so review whether each is really fixed."
            ),
            "link": "/dcma",
        })
    for ne in mc.get("no_effect") or []:
        if ne["reason"].startswith("Linked only"):
            out.append({
                "id": f"no-effect-{ne['code']}", "severity": "info", "area": "Model",
                "message": f"Risk {ne['code']} is linked only to completed or missing activities. Close it or re-link it.",
                "link": "/risk/register",
            })
    if mc.get("derived_probability"):
        out.append({
            "id": "derived-probability", "severity": "info", "area": "Model",
            "message": (
                f"{len(mc['derived_probability'])} quantified risk(s) use a probability derived from the 1–5 score "
                f"({', '.join(mc['derived_probability'][:5])}). Review them and enter a probability %."
            ),
            "link": "/risk/register",
        })
    return out


def run_summary(run: RiskSimulationRun) -> dict:
    r = run.results or {}
    pre = r.get("pre") or {}
    return {
        "id": str(run.id),
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "revision_label": run.revision_label,
        "data_date": run.data_date.date().isoformat() if run.data_date else None,
        "cpm_finish": r.get("cpm_finish"),
        "target_date": r.get("target_date"),
        "p10": pre.get("p10"), "p50": pre.get("p50"), "p80": pre.get("p80"), "p90": pre.get("p90"),
        "prob_meet_target": pre.get("prob_meet_target"),
        "prob_meet_cpm": pre.get("prob_meet_cpm"),
        "iterations": run.iterations,
    }
