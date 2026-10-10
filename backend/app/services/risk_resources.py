"""Risk > Resources: planned / earned / actual / remaining units per week, and
the earliest–latest finish the job's demonstrated production supports (see
engine/risk/resource_forecast.py for the method).

History comes from each schedule update's frozen snapshots: the earned units at
an update are the budget × physical % of that update's activities, and the
actual units come from its assignment snapshot (captured from migration 0027
on; earlier imports get theirs backfilled when re-applied from Program
Library). Materials are left out of productivity by default — tonnes of steel
delivered say nothing about how fast crews are working.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session, undefer

from app.engine.risk.resource_forecast import AssignmentInput, UpdatePoint, forecast
from app.models.baseline import Baseline, BaselineActivity, BaselineStatus
from app.models.resource import Resource
from app.models.resource_assignment import ResourceAssignment
from app.models.risk_analysis import RiskSimulationRun
from app.models.schedule_import import ScheduleImport
from app.services.risk_analysis import get_settings
from app.services.risk_network import current_programme_activities
from app.services.schedule_current import get_current_import, to_naive

TYPE_LABELS = {"RT_Labor": "Labor", "RT_Equip": "Nonlabor", "RT_Mat": "Material"}
_MAX_RESOURCE_ROWS = 25


def _history(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID):
    rows = (
        db.query(ScheduleImport)
        .options(undefer(ScheduleImport.activities_snapshot), undefer(ScheduleImport.assignments_snapshot))
        .filter(ScheduleImport.tenant_id == tenant_id, ScheduleImport.project_id == project_id)
        .all()
    )
    out = []
    for r in rows:
        dd = to_naive(r.data_date)
        if dd is None or not r.activities_snapshot:
            continue
        pct = {a["external_id"]: float(a.get("percent_complete") or 0) for a in r.activities_snapshot if a.get("external_id")}
        out.append((r.revision_label or r.filename, dd.date(), pct, r.assignments_snapshot or []))
    out.sort(key=lambda x: x[1])
    dedup = {}
    for item in out:
        dedup[item[1]] = item
    return [dedup[k] for k in sorted(dedup)]


def _update_points(history, budgets_live: dict[tuple[str, str], float], include) -> list[UpdatePoint]:
    """`include(rsrc_id, rsrc_type)` filters which assignments count."""
    points = []
    for label, dd, pct, snap in history:
        if snap:
            rows = [s for s in snap if include(s.get("rsrc_id"), s.get("rsrc_type"))]
            earned = sum((s.get("budget") or 0.0) * pct.get(s["external_id"], 0.0) / 100.0 for s in rows)
            actual = sum(s.get("actual") or 0.0 for s in rows)
        else:
            earned = sum(b * pct.get(ext, 0.0) / 100.0 for (ext, rid), b in budgets_live.items() if include(rid, None))
            actual = None
        points.append(UpdatePoint(label=label, data_date=dd, earned=earned, actual=actual))
    return points


def _fc_dict(fc) -> dict:
    return {
        "budget": fc.budget, "earned": fc.earned, "actual": fc.actual, "work_left": fc.work_left,
        "remaining_p6": fc.remaining_p6,
        "demonstrated_rate": fc.demonstrated_rate, "best_rate": fc.best_rate,
        "planned_peak_rate": fc.planned_peak_rate, "required_rate": fc.required_rate,
        "rate_ratio": fc.rate_ratio, "cumulative_productivity": fc.cumulative_productivity,
        "finish_p10": fc.finish_p10.isoformat() if fc.finish_p10 else None,
        "finish_p50": fc.finish_p50.isoformat() if fc.finish_p50 else None,
        "finish_p90": fc.finish_p90.isoformat() if fc.finish_p90 else None,
        "capped": fc.capped, "method": fc.method, "notes": fc.notes,
    }


def compute_resources(
    db: Session,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    rsrc_type: Optional[str] = None,
    resource_id: Optional[str] = None,
) -> dict:
    settings = get_settings(db, tenant_id, project_id)
    current = get_current_import(db, tenant_id, project_id)
    dd = to_naive(current.data_date).date() if current is not None and current.data_date else date.today()
    baseline = (
        db.query(Baseline)
        .filter(Baseline.tenant_id == tenant_id, Baseline.project_id == project_id, Baseline.status == BaselineStatus.active)
        .first()
    )
    target = settings.target_date or (baseline.target_end_date if baseline else None)

    acts = {a.id: a for a in current_programme_activities(db, tenant_id, project_id)}
    base_dates: dict[uuid.UUID, tuple[Optional[date], Optional[date]]] = {}
    if baseline:
        for ba in db.query(BaselineActivity).filter(BaselineActivity.baseline_id == baseline.id):
            base_dates[ba.activity_id] = (ba.baseline_start, ba.baseline_end)

    resources = {r.id: r for r in db.query(Resource).filter(Resource.tenant_id == tenant_id, Resource.project_id == project_id)}
    rows = []
    for ra in db.query(ResourceAssignment).filter(
        ResourceAssignment.tenant_id == tenant_id, ResourceAssignment.project_id == project_id
    ):
        a = acts.get(ra.activity_id)
        res = resources.get(ra.resource_id)
        if a is None or res is None:
            continue
        ps, pf = base_dates.get(a.id, (None, None))
        ps = ps or a.planned_start or a.early_start
        pf = pf or a.planned_finish or a.early_finish
        rows.append((
            AssignmentInput(
                activity_key=a.external_id, budget=ra.target_qty or 0.0, actual=ra.act_reg_qty or 0.0,
                remaining=ra.remain_qty or 0.0, percent_complete=float(a.percent_complete or 0),
                planned_start=ps, planned_finish=pf,
                forecast_start=a.early_start, forecast_finish=a.early_finish,
            ),
            res,
        ))

    types_present = sorted({res.rsrc_type for _, res in rows})
    if rsrc_type is None:
        rsrc_type = "RT_Labor" if "RT_Labor" in types_present else next((t for t in types_present if t != "RT_Mat"), None)

    def include(rid: Optional[str], rtype: Optional[str]) -> bool:
        if resource_id and rid != resource_id:
            return False
        if rtype is not None and rsrc_type and rtype != rsrc_type:
            return False
        if rtype is None and rsrc_type and rid is not None:
            r = rsrc_by_code.get(rid)
            return r is not None and r.rsrc_type == rsrc_type
        return True

    rsrc_by_code = {res.rsrc_id: res for _, res in rows}
    selected = [(a, res) for a, res in rows if include(res.rsrc_id, res.rsrc_type)]
    budgets_live: dict[tuple[str, str], float] = defaultdict(float)
    for a, res in rows:
        budgets_live[(a.activity_key, res.rsrc_id)] += a.budget

    history = _history(db, tenant_id, project_id)
    total = forecast([a for a, _ in selected], _update_points(history, budgets_live, include), dd, target_finish=target)

    # Per-resource table, largest budgets first.
    by_res: dict[str, list[AssignmentInput]] = defaultdict(list)
    for a, res in selected:
        by_res[res.rsrc_id].append(a)
    per_resource = []
    for rid, items in sorted(by_res.items(), key=lambda kv: -sum(x.budget for x in kv[1]))[:_MAX_RESOURCE_ROWS]:
        res = rsrc_by_code[rid]
        fc = forecast(
            items,
            _update_points(history, budgets_live, lambda r, t, rid=rid: r == rid),
            dd,
            target_finish=target,
        )
        per_resource.append({
            "rsrc_id": rid, "name": res.name, "type": TYPE_LABELS.get(res.rsrc_type, res.rsrc_type),
            "unit": res.unit_id, **_fc_dict(fc),
            "last_productivity": [p.productivity for p in fc.periods[-3:]],
        })

    latest_run = (
        db.query(RiskSimulationRun)
        .filter(RiskSimulationRun.tenant_id == tenant_id, RiskSimulationRun.project_id == project_id)
        .order_by(RiskSimulationRun.created_at.desc())
        .first()
    )
    qsra = None
    if latest_run:
        pre = (latest_run.results or {}).get("pre") or {}
        qsra = {"p10": pre.get("p10"), "p50": pre.get("p50"), "p90": pre.get("p90"),
                "cpm_finish": (latest_run.results or {}).get("cpm_finish"),
                "run_at": latest_run.created_at.isoformat() if latest_run.created_at else None}

    return {
        "data_date": dd.isoformat(),
        "target_date": target.isoformat() if target else None,
        "types": [{"value": t, "label": TYPE_LABELS.get(t, t)} for t in types_present],
        "rsrc_type": rsrc_type,
        "resource_id": resource_id,
        "resources": sorted(
            [{"rsrc_id": res.rsrc_id, "name": res.name, "type": res.rsrc_type} for res in {r.id: r for _, r in rows}.values()],
            key=lambda r: r["name"],
        ),
        "unit": (selected[0][1].unit_id if selected and len({r.unit_id for _, r in selected}) == 1 else None),
        "total": _fc_dict(total),
        "weeks": [
            {"week": w.week.isoformat(), "planned": w.planned, "earned": w.earned, "actual": w.actual, "remaining": w.remaining}
            for w in total.weeks
        ],
        "periods": [
            {"label": p.label, "start": p.start.isoformat(), "end": p.end.isoformat(), "weeks": p.weeks,
             "earned": p.earned, "actual": p.actual, "rate": p.rate, "productivity": p.productivity}
            for p in total.periods
        ],
        "per_resource": per_resource,
        "snapshots_with_actuals": sum(1 for h in history if h[3]),
        "updates": len(history),
        "qsra": qsra,
    }


def resource_recommendations(data: dict) -> list[dict]:
    out = []
    for row in data.get("per_resource", []):
        ratio = row.get("rate_ratio")
        if ratio and ratio > 1.10 and row.get("demonstrated_rate"):
            unit = row.get("unit") or "units"
            out.append({
                "id": f"productivity-{row['rsrc_id']}",
                "severity": "red" if ratio > 1.25 else "amber",
                "area": "Resources",
                "message": (
                    f"{row['name']}: finishing by {data.get('target_date')} needs {row['required_rate']:,.0f} {unit}/week "
                    f"earned; recent updates averaged {row['demonstrated_rate']:,.0f}, so a {100 * (ratio - 1):.0f}% "
                    f"improvement is required. Add crews or shifts, or re-forecast."
                ),
                "link": "/risk/resources",
            })
    return out
