import uuid
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission
from app.engine.risk.monte_carlo import ActivityRiskOverride, run_monte_carlo
from app.models.activity import Activity
from app.models.activity_relationship import ActivityRelationship
from app.models.calendar import Calendar
from app.models.project import Project
from app.models.risk_analysis import RiskSimulationRun
from app.models.user_tenant_role import TenantRole
from app.schemas.risk import MonteCarloRequest, MonteCarloResultOut
from app.services import risk_analysis, risk_resources, risk_signals
from app.services.schedule_current import get_current_import, to_naive

router = APIRouter(prefix="/projects/{project_id}/risk", tags=["risk"])


@router.post("/monte-carlo", response_model=MonteCarloResultOut)
def run_monte_carlo_simulation(
    project_id: uuid.UUID,
    payload: MonteCarloRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> MonteCarloResultOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)

    activities = db.query(Activity).filter(Activity.tenant_id == ctx.tenant_id, Activity.project_id == project_id).all()
    activity_ids = {a.id for a in activities}
    relationships = (
        db.query(ActivityRelationship)
        .filter(ActivityRelationship.tenant_id == ctx.tenant_id, ActivityRelationship.project_id == project_id)
        .all()
        if activity_ids
        else []
    )

    calendars = db.query(Calendar).filter(Calendar.tenant_id == ctx.tenant_id, Calendar.project_id == project_id).all()
    calendars_by_id = {c.id: c.hours_per_day for c in calendars}
    default_hpd = calendars[0].hours_per_day if calendars else 8.0

    last_import = get_current_import(db, ctx.tenant_id, project_id)
    data_date = to_naive(last_import.data_date) if last_import else None

    overrides = [
        ActivityRiskOverride(
            activity_id=o.activity_id, optimistic=o.optimistic, most_likely=o.most_likely, pessimistic=o.pessimistic
        )
        for o in payload.overrides
        if o.activity_id in activity_ids
    ]

    try:
        result = run_monte_carlo(
            activities,
            relationships,
            calendars_by_id,
            default_hpd,
            data_date,
            iterations=payload.iterations,
            spread=payload.spread,
            overrides=overrides,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return MonteCarloResultOut.model_validate(result)


# --- QSRA (risk-driver Monte Carlo) -----------------------------------------------
# The endpoint above stays for the Reporting block that already uses it; the
# Risk section runs the register-driven analysis below (services/risk_analysis.py).


def _company_view(db: Session, project_id: uuid.UUID, ctx: AuthContext) -> None:
    """Risk analysis is company-side. Subcontractors aren't gated by
    require_project_permission (their access is scope-based), so they're
    excluded explicitly."""
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    if ctx.role == TenantRole.subcontractor:
        raise HTTPException(status_code=403, detail="Not permitted")
    require_project_permission(db, project_id, ctx)


def _company_edit(db: Session, project_id: uuid.UUID, ctx: AuthContext) -> None:
    _company_view(db, project_id, ctx)
    require_project_permission(db, project_id, ctx, need_edit=True)


class QsraSettingsIn(BaseModel):
    confidence: Optional[Literal["high", "medium", "low"]] = None
    iterations: Optional[int] = Field(default=None, ge=200, le=5000)
    target_date: Optional[date] = None
    finish_activity_external_id: Optional[str] = Field(default=None, max_length=50)
    near_critical_days: Optional[float] = Field(default=None, ge=0, le=100)
    correlate_by_wbs: Optional[bool] = None


def _settings_out(s) -> dict:
    return {
        "confidence": s.confidence,
        "confidence_options": [
            {"value": k, "label": risk_analysis.CONFIDENCE_LABELS[k], "range": list(v)}
            for k, v in risk_analysis.CONFIDENCE_RANGES.items()
        ],
        "iterations": s.iterations,
        "seed": s.seed,
        "target_date": s.target_date.isoformat() if s.target_date else None,
        "finish_activity_external_id": s.finish_activity_external_id,
        "near_critical_days": s.near_critical_days,
        "correlate_by_wbs": s.correlate_by_wbs,
    }


@router.get("/qsra/settings")
def get_qsra_settings(
    project_id: uuid.UUID, db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)
) -> dict:
    _company_view(db, project_id, ctx)
    settings = risk_analysis.get_settings(db, ctx.tenant_id, project_id)
    db.commit()
    out = _settings_out(settings)
    bf = risk_analysis.baseline_finish(db, ctx.tenant_id, project_id)
    out["baseline_finish"] = bf.isoformat() if bf else None
    return out


@router.put("/qsra/settings")
def update_qsra_settings(
    project_id: uuid.UUID,
    payload: QsraSettingsIn,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> dict:
    _company_edit(db, project_id, ctx)
    settings = risk_analysis.get_settings(db, ctx.tenant_id, project_id)
    changes = payload.model_dump(exclude_unset=True)
    for field in ("confidence", "iterations", "near_critical_days", "correlate_by_wbs"):
        if changes.get(field) is not None:
            setattr(settings, field, changes[field])
    # These two are clearable.
    if "target_date" in changes:
        settings.target_date = changes["target_date"]
    if "finish_activity_external_id" in changes:
        settings.finish_activity_external_id = (changes["finish_activity_external_id"] or "").strip() or None
    db.commit()
    db.refresh(settings)
    return _settings_out(settings)


def _run_out(run: RiskSimulationRun) -> dict:
    return {
        **risk_analysis.run_summary(run),
        "duration_ms": run.duration_ms,
        "seed": run.seed,
        "settings": run.settings,
        "inputs": run.inputs,
        "results": run.results,
        "ranking": run.ranking,
    }


def _latest_run(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> Optional[RiskSimulationRun]:
    return (
        db.query(RiskSimulationRun)
        .filter(RiskSimulationRun.tenant_id == tenant_id, RiskSimulationRun.project_id == project_id)
        .order_by(RiskSimulationRun.created_at.desc())
        .first()
    )


@router.post("/qsra/runs")
def create_qsra_run(
    project_id: uuid.UUID, db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)
) -> dict:
    _company_edit(db, project_id, ctx)
    try:
        run = risk_analysis.run_qsra(db, ctx.tenant_id, project_id, ctx.user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _run_out(run)


@router.get("/qsra/runs")
def list_qsra_runs(
    project_id: uuid.UUID,
    limit: int = Query(default=30, ge=1, le=200),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> list[dict]:
    _company_view(db, project_id, ctx)
    runs = (
        db.query(RiskSimulationRun)
        .filter(RiskSimulationRun.tenant_id == ctx.tenant_id, RiskSimulationRun.project_id == project_id)
        .order_by(RiskSimulationRun.created_at.desc())
        .limit(limit)
        .all()
    )
    return [risk_analysis.run_summary(r) for r in reversed(runs)]


@router.get("/qsra/runs/latest")
def latest_qsra_run(
    project_id: uuid.UUID, db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)
) -> Optional[dict]:
    _company_view(db, project_id, ctx)
    run = _latest_run(db, ctx.tenant_id, project_id)
    return _run_out(run) if run else None


def _load_run(db: Session, project_id: uuid.UUID, run_id: uuid.UUID, ctx: AuthContext) -> RiskSimulationRun:
    run = get_tenant_scoped_or_404(db, RiskSimulationRun, run_id, ctx)
    if run.project_id != project_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/qsra/runs/{run_id}")
def get_qsra_run(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> dict:
    _company_view(db, project_id, ctx)
    return _run_out(_load_run(db, project_id, run_id, ctx))


@router.post("/qsra/runs/{run_id}/ranking")
def rank_qsra_run(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> dict:
    _company_edit(db, project_id, ctx)
    run = _load_run(db, project_id, run_id, ctx)
    try:
        run = risk_analysis.run_ranking(db, run, ctx.tenant_id, project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _run_out(run)


@router.get("/early-warnings")
def get_early_warnings(
    project_id: uuid.UUID, db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)
) -> dict:
    _company_view(db, project_id, ctx)
    data = risk_signals.compute_signals(db, ctx.tenant_id, project_id)
    db.commit()  # the settings row may have been created on first read
    return data


@router.get("/resources")
def get_resource_analysis(
    project_id: uuid.UUID,
    rsrc_type: Optional[str] = Query(default=None, max_length=20),
    resource_id: Optional[str] = Query(default=None, max_length=50),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> dict:
    _company_view(db, project_id, ctx)
    data = risk_resources.compute_resources(db, ctx.tenant_id, project_id, rsrc_type=rsrc_type, resource_id=resource_id)
    db.commit()
    return data


@router.get("/recommendations")
def get_recommendations(
    project_id: uuid.UUID, db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)
) -> dict:
    """Every rule-based recommendation in one list: the latest QSRA run's, the
    early warnings', and the resource productivity checks'."""
    _company_view(db, project_id, ctx)
    run = _latest_run(db, ctx.tenant_id, project_id)
    items: list[dict] = list((run.results or {}).get("recommendations", [])) if run else []
    items += risk_signals.signal_recommendations(risk_signals.compute_signals(db, ctx.tenant_id, project_id))
    items += risk_resources.resource_recommendations(risk_resources.compute_resources(db, ctx.tenant_id, project_id))
    db.commit()
    order = {"red": 0, "amber": 1, "info": 2}
    items.sort(key=lambda r: order.get(r.get("severity"), 3))
    return {"run": risk_analysis.run_summary(run) if run else None, "items": items}
