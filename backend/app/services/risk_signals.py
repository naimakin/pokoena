"""Early warnings — weak signals read from successive schedule updates.

Every indicator here is computed from what each P6 update already leaves
behind (the frozen per-import activity snapshots, the baseline, saved QSRA
runs), so it needs no extra input from anyone. Each one answers a question a
project manager should be asking before the finish date moves, not after:

  1  Finish slip trend     — is the forecast finish sliding update after update?
  2  Finish margin         — how much buffer is left to the target, and how fast is it burning?
  3  Baseline execution    — are activities finishing when the baseline said (DCMA BEI)?
  4  Missed starts         — are activities that were due to start actually starting?
  5  Stuck activities      — in-progress work whose remaining duration keeps growing ("90% complete")
  6  Near-critical density — how much remaining work has little or no float?
  7  Forecast reliability  — did last update's one-period look-ahead happen (NASA CEI)?
  8  Critical-path churn   — did the driving path jump to new activities?
  9  Hidden compression    — the finish held, but only by shortening critical work
  10 QSRA confidence trend — is the probability of finishing on time falling?

Thresholds are the defaults the research brief proposes: those marked [DCMA]
or [Lipke] come from published guidance, the rest are practitioner
heuristics, stated as such in the UI.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.engine.durations import activity_days, valid_hours_per_day
from app.models.activity import Activity
from app.models.baseline import Baseline, BaselineActivity, BaselineStatus
from app.models.risk_analysis import RiskSimulationRun
from app.models.schedule_import import ScheduleImport
from app.services.risk_analysis import get_settings
from app.services.risk_network import current_programme_activities
from app.services.schedule_current import to_naive


@dataclass
class Indicator:
    id: str
    name: str
    question: str
    status: str  # good | amber | red | na
    value: str
    detail: str
    basis: str  # "DCMA" / "heuristic" / …
    series: list[dict] = field(default_factory=list)  # [{label, value}]
    items: list[dict] = field(default_factory=list)  # drill-down rows


def _d(s: Optional[str]) -> Optional[date]:
    return date.fromisoformat(s) if s else None


def working_days(a: date, b: date) -> float:
    """Mon–Fri days from a to b (negative when b < a). Good enough for trend
    rates; the precise calendars live in the CPM, not in these ratios."""
    if a == b:
        return 0.0
    sign = 1.0
    if b < a:
        a, b, sign = b, a, -1.0
    days = (b - a).days
    full, rest = divmod(days, 7)
    wd = full * 5
    d = a
    for _ in range(rest):
        d += timedelta(days=1)
        if d.weekday() < 5:
            wd += 1
    return sign * wd


@dataclass
class Update:
    label: str
    data_date: date
    acts: dict[str, dict]  # external_id -> snapshot row

    def finish(self, finish_id: Optional[str]) -> Optional[date]:
        if finish_id and finish_id in self.acts:
            row = self.acts[finish_id]
            return _d(row.get("actual_finish")) or _d(row.get("early_finish"))
        best = None
        for row in self.acts.values():
            f = _d(row.get("actual_finish")) or _d(row.get("early_finish"))
            if f and (best is None or f > best):
                best = f
        return best


def load_updates(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> list[Update]:
    rows = (
        db.query(ScheduleImport)
        .filter(ScheduleImport.tenant_id == tenant_id, ScheduleImport.project_id == project_id)
        .all()
    )
    out = []
    for r in rows:
        dd = to_naive(r.data_date)
        if dd is None or not r.activities_snapshot:
            continue
        acts = {a["external_id"]: a for a in r.activities_snapshot if a.get("external_id")}
        out.append(Update(label=r.revision_label or r.filename, data_date=dd.date(), acts=acts))
    out.sort(key=lambda u: u.data_date)
    # One point per data date: re-uploads of the same update keep the latest.
    dedup: dict[date, Update] = {}
    for u in out:
        dedup[u.data_date] = u
    return [dedup[k] for k in sorted(dedup)]


def _status(value: Optional[float], amber: float, red: float, higher_is_worse: bool = True) -> str:
    if value is None:
        return "na"
    if higher_is_worse:
        return "red" if value >= red else "amber" if value >= amber else "good"
    return "red" if value <= red else "amber" if value <= amber else "good"


def compute_signals(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> dict:
    settings = get_settings(db, tenant_id, project_id)
    updates = load_updates(db, tenant_id, project_id)
    finish_id = settings.finish_activity_external_id
    baseline = (
        db.query(Baseline)
        .filter(Baseline.tenant_id == tenant_id, Baseline.project_id == project_id, Baseline.status == BaselineStatus.active)
        .first()
    )
    target = settings.target_date or (baseline.target_end_date if baseline else None)
    near_days = settings.near_critical_days
    live = current_programme_activities(db, tenant_id, project_id)
    # Hours read in days on each activity's own calendar (engine/durations.py).
    # Snapshot rows carry it since hours_per_day was frozen into them; older
    # ones borrow the live activity's.
    live_hpd = {a.external_id: a.hours_per_day for a in live}

    def row_days(e: str, row: dict, key: str) -> float:
        return (row.get(key) or 0.0) / valid_hours_per_day(row.get("hours_per_day") or live_hpd.get(e))

    indicators: list[Indicator] = []
    n = len(updates)
    last = updates[-1] if updates else None
    prev = updates[-2] if n >= 2 else None

    # 1. Finish slip trend ------------------------------------------------------
    finishes = [(u, u.finish(finish_id)) for u in updates]
    series = [{"label": u.label, "value": f.isoformat() if f else None} for u, f in finishes]
    slips = 0
    for (_u0, f0), (_u1, f1) in zip(finishes, finishes[1:]):
        if f0 and f1 and f1 > f0:
            slips += 1
        else:
            slips = 0
    if n >= 2 and finishes[-1][1] and finishes[max(0, n - 4)][1]:
        u0, f0 = finishes[max(0, n - 4)]
        u1, f1 = finishes[-1]
        elapsed = (u1.data_date - u0.data_date).days
        rate = (f1 - f0).days / elapsed if elapsed > 0 else 0.0
        projected = None
        if rate < 0.9:
            remaining = (f1 - u1.data_date).days
            projected = u1.data_date + timedelta(days=remaining / (1 - rate)) if rate > 0 else f1
        status = "red" if rate >= 0.25 or slips >= 3 or (projected and target and projected > target) else (
            "amber" if rate >= 0.10 or slips >= 2 else "good"
        )
        value = f"{rate * 30:+.1f} days per month" if rate else "Holding"
        detail = (
            f"The forecast finish moved {(f1 - f0).days:+d} days over the last {elapsed} days of updates"
            + (f", slipping in {slips} consecutive update(s)" if slips else "")
            + (f". If the trend continues, completion lands around {projected.strftime('%d-%b-%Y')}." if projected and rate > 0 else ".")
            + (" At this rate the finish keeps moving faster than time passes — it is diverging." if rate >= 0.9 else "")
        )
        indicators.append(Indicator("slip", "Finish slip trend", "Is the forecast finish sliding update after update?",
                                    status, value, detail, "heuristic", series,
                                    [{"label": "Trend-projected finish", "value": projected.isoformat() if projected else None},
                                     {"label": "Consecutive slips", "value": slips}]))
    else:
        indicators.append(Indicator("slip", "Finish slip trend", "Is the forecast finish sliding update after update?",
                                    "na", "Needs 2 updates", "Upload at least two schedule updates to see a trend.",
                                    "heuristic", series))

    # 2. Finish margin / erosion --------------------------------------------------
    if target and finishes and finishes[-1][1]:
        margins = [(u, working_days(f, target)) for u, f in finishes if f]
        m_now = margins[-1][1]
        erosion = None
        time_to_zero = None
        if len(margins) >= 2:
            (u0, m0), (u1, m1) = margins[-2], margins[-1]
            dt = (u1.data_date - u0.data_date).days
            erosion = (m0 - m1) / dt * 30 if dt > 0 else None  # working days lost per month
            if erosion and erosion > 0 and m_now > 0:
                time_to_zero = m_now / erosion  # months
        status = "red" if m_now <= 0 else ("amber" if (time_to_zero is not None and time_to_zero < 3) else "good")
        detail = (
            f"{m_now:+.0f} working days between the forecast finish and the target ({target.strftime('%d-%b-%Y')})."
            + (f" Losing about {erosion:.1f} working days a month" if erosion and erosion > 0 else "")
            + (f" — at that rate the margin is gone in {time_to_zero:.1f} months." if time_to_zero else ".")
        )
        indicators.append(Indicator("margin", "Finish margin", "How much buffer is left, and how fast is it burning?",
                                    status, f"{m_now:+.0f} working days", detail, "heuristic",
                                    [{"label": u.label, "value": round(m, 1)} for u, m in margins]))
    else:
        indicators.append(Indicator("margin", "Finish margin", "How much buffer is left, and how fast is it burning?",
                                    "na", "No target", "Set a target date in QSRA settings, or lock a baseline.",
                                    "heuristic"))

    # 3. Baseline execution index (DCMA #14) ----------------------------------------
    if baseline and last:
        rows = (
            db.query(BaselineActivity, Activity.external_id)
            .join(Activity, Activity.id == BaselineActivity.activity_id)
            .filter(BaselineActivity.baseline_id == baseline.id)
            .all()
        )
        base_end = {ext: ba.baseline_end for ba, ext in rows if ba.baseline_end}
        bei_series = []
        for u in updates:
            due = [e for e, d in base_end.items() if d <= u.data_date]
            done = [e for e, row in u.acts.items() if _d(row.get("actual_finish")) and _d(row.get("actual_finish")) <= u.data_date]
            if due:
                bei_series.append({"label": u.label, "value": round(len(done) / len(due), 2)})
        if bei_series:
            bei = bei_series[-1]["value"]
            late = [e for e, d in base_end.items() if d <= last.data_date and not _d(last.acts.get(e, {}).get("actual_finish"))]
            indicators.append(Indicator(
                "bei", "Baseline execution (BEI)", "Are activities finishing when the baseline said they would?",
                _status(bei, 0.95, 0.85, higher_is_worse=False), f"{bei:.2f}",
                f"{bei:.2f} activities completed for every one the baseline had due by the data date "
                f"(DCMA target ≥ 0.95). {len(late)} baseline-due activities are still open.",
                "DCMA", bei_series,
                [{"external_id": e, "name": (last.acts.get(e) or {}).get("name", ""), "baseline_finish": base_end[e].isoformat()}
                 for e in sorted(late, key=lambda x: base_end[x])[:20]],
            ))
        else:
            indicators.append(Indicator("bei", "Baseline execution (BEI)", "Are activities finishing when the baseline said they would?",
                                        "na", "Nothing due yet", "No baseline activity is due by the data date yet.", "DCMA"))
    else:
        indicators.append(Indicator("bei", "Baseline execution (BEI)", "Are activities finishing when the baseline said they would?",
                                    "na", "No baseline", "Lock a baseline to measure execution against it.", "DCMA"))

    # 4. Missed starts / 7. forecast reliability / 5. stuck / 8. churn / 9. compression
    if prev and last:
        # Missed starts: due to start by now per the previous update, still not started.
        due_start = [
            e for e, row in prev.acts.items()
            if row.get("status") == "not_started" and _d(row.get("early_start")) and _d(row.get("early_start")) <= last.data_date
            and e in last.acts
        ]
        missed = [e for e in due_start if last.acts[e].get("status") == "not_started"]
        ratio = len(missed) / len(due_start) if due_start else None
        indicators.append(Indicator(
            "missed-starts", "Missed starts", "Are activities that were due to start actually starting?",
            _status(ratio, 0.15, 0.30) if ratio is not None else "na",
            f"{len(missed)} of {len(due_start)}" if due_start else "None due",
            (f"{ratio:.0%} of the activities {prev.label} planned to start by {last.data_date.strftime('%d-%b-%Y')} "
             f"haven't started. Starts lead finishes — this is the earliest sign of a future slip.")
            if due_start else "No activity was forecast to start in the last update period.",
            "heuristic", [],
            [{"external_id": e, "name": last.acts[e].get("name", ""), "planned_start": prev.acts[e].get("early_start")}
             for e in missed[:20]],
        ))

        # Forecast reliability (CEI): forecast to finish this period — did they?
        window = [
            e for e, row in prev.acts.items()
            if row.get("status") != "complete" and _d(row.get("early_finish"))
            and prev.data_date < _d(row.get("early_finish")) <= last.data_date and e in last.acts
        ]
        hit = [e for e in window if last.acts[e].get("status") == "complete"]
        cei = len(hit) / len(window) if window else None
        indicators.append(Indicator(
            "cei", "Forecast reliability (CEI)", "Did last update's look-ahead actually happen?",
            _status(cei, 0.75, 0.50, higher_is_worse=False) if cei is not None else "na",
            f"{cei:.2f}" if cei is not None else "Nothing due",
            (f"{len(hit)} of the {len(window)} activities {prev.label} forecast to finish this period did. "
             f"If the team can't hit its own one-period forecast, discount the rest of it.")
            if window else "No activity was forecast to finish in the last update period.",
            "heuristic (NASA CEI)", [],
            [{"external_id": e, "name": last.acts[e].get("name", ""), "forecast_finish": prev.acts[e].get("early_finish")}
             for e in window if e not in hit][:20],
        ))

        # Stuck activities: remaining duration not burning down while in progress.
        elapsed_d = working_days(prev.data_date, last.data_date)
        stuck = []
        in_prog = 0
        for e, row in last.acts.items():
            p = prev.acts.get(e)
            if not p or row.get("status") != "in_progress" or p.get("status") != "in_progress":
                continue
            in_prog += 1
            rd0 = row_days(e, p, "remaining_duration_hours")
            rd1 = row_days(e, row, "remaining_duration_hours")
            growth = rd1 - max(0.0, rd0 - elapsed_d)
            pct_same = (row.get("percent_complete") or 0) <= (p.get("percent_complete") or 0)
            if growth > 1.0 or pct_same:
                stuck.append({
                    "external_id": e, "name": row.get("name", ""),
                    "percent_complete": row.get("percent_complete"),
                    "growth_days": round(growth, 1),
                    "critical": bool(row.get("is_critical")),
                })
        crit_stuck = [s for s in stuck if s["critical"]]
        ratio = len(stuck) / in_prog if in_prog else None
        status = "red" if len(crit_stuck) >= 2 else ("amber" if crit_stuck or (ratio is not None and ratio > 0.10) else "good")
        indicators.append(Indicator(
            "stuck", "Stuck activities", "Is in-progress work actually burning down?",
            status if in_prog else "na",
            f"{len(stuck)} of {in_prog}" if in_prog else "None in progress",
            (f"{len(stuck)} in-progress activities grew their remaining duration or didn't move their % complete "
             f"since {prev.label}; {len(crit_stuck)} of them are critical. The classic '90% complete' pattern.")
            if in_prog else "No activity was in progress in both of the last two updates.",
            "heuristic", [], sorted(stuck, key=lambda s: (not s["critical"], -s["growth_days"]))[:20],
        ))

        # Critical-path churn: Jaccard of the open critical sets.
        c0 = {e for e, r in prev.acts.items() if r.get("is_critical") and r.get("status") != "complete"}
        c1 = {e for e, r in last.acts.items() if r.get("is_critical") and r.get("status") != "complete"}
        if c0 or c1:
            jac = len(c0 & c1) / len(c0 | c1)
            new_on = sorted(c1 - c0)
            indicators.append(Indicator(
                "churn", "Critical-path stability", "Did the driving path jump to new activities?",
                _status(jac, 0.6, 0.4, higher_is_worse=False), f"{jac:.0%} unchanged",
                f"{len(new_on)} activities joined the critical path since {prev.label}. A jump usually means a new "
                f"driver has emerged — often procurement or a subcontractor.",
                "heuristic", [],
                [{"external_id": e, "name": last.acts[e].get("name", "")} for e in new_on[:20]],
            ))

        # Hidden compression: finish held while critical durations were cut.
        f0, f1 = prev.finish(finish_id), last.finish(finish_id)
        cut_days = 0.0
        cuts = []
        for e, row in last.acts.items():
            p = prev.acts.get(e)
            if not p or p.get("status") != "not_started" or row.get("status") != "not_started" or not p.get("is_critical"):
                continue
            r0 = row_days(e, p, "remaining_duration_hours")
            r1 = row_days(e, row, "remaining_duration_hours")
            if r0 - r1 > 0:
                cut_days += r0 - r1
                cuts.append({"external_id": e, "name": row.get("name", ""), "cut_days": round(r0 - r1, 1)})
        held = f0 and f1 and abs((f1 - f0).days) <= 2
        status = "na" if not (f0 and f1) else ("red" if held and cut_days > 15 else "amber" if held and cut_days > 5 else "good")
        indicators.append(Indicator(
            "compression", "Hidden compression", "Did the finish hold only because critical work was squeezed?",
            status, f"{cut_days:.0f} days cut",
            (f"{cut_days:.0f} working days were taken out of not-started critical activities since {prev.label}"
             + (" while the finish barely moved — confirm a recovery plan backs these cuts." if held and cut_days > 5 else "."))
            if cuts else "No not-started critical activity was shortened in the last update.",
            "heuristic", [], sorted(cuts, key=lambda c: -c["cut_days"])[:20],
        ))
    else:
        for iid, name, q in (
            ("missed-starts", "Missed starts", "Are activities that were due to start actually starting?"),
            ("cei", "Forecast reliability (CEI)", "Did last update's look-ahead actually happen?"),
            ("stuck", "Stuck activities", "Is in-progress work actually burning down?"),
            ("churn", "Critical-path stability", "Did the driving path jump to new activities?"),
            ("compression", "Hidden compression", "Did the finish hold only because critical work was squeezed?"),
        ):
            indicators.append(Indicator(iid, name, q, "na", "Needs 2 updates",
                                        "Compares consecutive updates — upload another one.", "heuristic"))

    # 6. Near-critical density (live) + negative-float trend -------------------------
    open_acts = [a for a in live if a.status.value != "complete" and (a.task_type or "") not in ("TT_WBS", "TT_LOE")]
    if open_acts:
        near = [a for a in open_acts if a.total_float_hours is not None and activity_days(a, a.total_float_hours) <= near_days]
        negative = [a for a in open_acts if a.total_float_hours is not None and a.total_float_hours < 0]
        density = len(near) / len(open_acts)
        neg_series = [
            {"label": u.label, "value": sum(1 for r in u.acts.values()
                                            if r.get("status") != "complete" and (r.get("total_float_hours") or 0) < 0)}
            for u in updates
        ]
        rising = len(neg_series) >= 3 and neg_series[-1]["value"] > neg_series[-2]["value"] > neg_series[-3]["value"]
        status = "red" if density > 0.40 or rising else ("amber" if density > 0.25 or negative else "good")
        by_wbs: dict[str, list[Activity]] = {}
        for a in open_acts:
            by_wbs.setdefault(a.wbs_path or "—", []).append(a)
        hot = []
        for w, acts in by_wbs.items():
            if len(acts) < 10:
                continue
            nd = sum(1 for a in acts if a.total_float_hours is not None and activity_days(a, a.total_float_hours) <= near_days)
            if nd / len(acts) > 0.40:
                hot.append({"wbs": w, "density_pct": round(100 * nd / len(acts)), "activities": len(acts)})
        indicators.append(Indicator(
            "density", "Near-critical density", "How much remaining work has little or no float?",
            status, f"{density:.0%}",
            f"{len(near)} of {len(open_acts)} remaining activities have {near_days:.0f} working days of float or less; "
            f"{len(negative)} are negative. The more paths near zero float, the less credible the deterministic date "
            f"(merge bias).",
            "heuristic", neg_series, sorted(hot, key=lambda h: -h["density_pct"])[:10],
        ))

    # 10. QSRA confidence trend --------------------------------------------------------
    runs = (
        db.query(RiskSimulationRun)
        .filter(RiskSimulationRun.tenant_id == tenant_id, RiskSimulationRun.project_id == project_id)
        .order_by(RiskSimulationRun.created_at)
        .all()
    )
    conf = [
        {"label": r.revision_label or r.created_at.date().isoformat(),
         "value": (r.results.get("pre") or {}).get("prob_meet_target"),
         "p80": (r.results.get("pre") or {}).get("p80")}
        for r in runs
    ]
    conf = [c for c in conf if c["value"] is not None]
    if conf:
        latest = conf[-1]["value"]
        falling = len(conf) >= 3 and conf[-1]["value"] < conf[-2]["value"] < conf[-3]["value"]
        status = "red" if latest < 50 and falling else ("amber" if latest < 50 or falling else "good")
        indicators.append(Indicator(
            "confidence", "Confidence of finishing on time", "Is the probability of meeting the target falling?",
            status, f"{latest:.0f}%",
            f"The latest QSRA gives a {latest:.0f}% probability of meeting the target"
            + (", and it has fallen in each of the last runs." if falling else "."),
            "heuristic", conf,
        ))
    else:
        indicators.append(Indicator("confidence", "Confidence of finishing on time",
                                    "Is the probability of meeting the target falling?", "na", "No runs yet",
                                    "Run a QSRA (with a target date) to start this trend.", "heuristic"))

    order = {"red": 0, "amber": 1, "good": 2, "na": 3}
    return {
        "updates": [{"label": u.label, "data_date": u.data_date.isoformat()} for u in updates],
        "target_date": target.isoformat() if target else None,
        "near_critical_days": near_days,
        "indicators": [i.__dict__ for i in sorted(indicators, key=lambda i: order[i.status])],
    }


def signal_recommendations(signals: dict) -> list[dict]:
    out = []
    for ind in signals.get("indicators", []):
        if ind["status"] not in ("red", "amber"):
            continue
        sev = ind["status"]
        iid = ind["id"]
        if iid == "slip":
            msg = f"Persistent slip: {ind['detail']}"
        elif iid == "margin":
            msg = f"Finish margin: {ind['detail']}"
        elif iid == "stuck":
            crit = [s for s in ind["items"] if s.get("critical")]
            if crit:
                s = crit[0]
                msg = (f"{s['external_id']} — {s['name']} ({s.get('percent_complete', 0)}% complete) isn't burning down "
                       f"and is on the critical path. Obtain a firm finish commitment.")
            else:
                msg = ind["detail"]
        elif iid == "compression":
            msg = ind["detail"]
        elif iid == "density":
            hot = ind["items"][:1]
            msg = (f"{hot[0]['density_pct']}% of the remaining work in WBS {hot[0]['wbs']} has little or no float. "
                   f"Any slip there reaches the finish.") if hot else ind["detail"]
        else:
            msg = ind["detail"]
        out.append({"id": f"signal-{iid}", "severity": sev, "area": "Early warning", "message": msg,
                    "link": "/risk/early-warnings"})
    return out

