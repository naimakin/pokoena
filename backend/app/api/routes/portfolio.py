"""Portfolio Dashboard (Portfolio > Portfolio Dashboard) — see services/portfolio.py."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.cache import cached_json, project_scopes
from app.db.session import get_db
from app.deps import AuthContext, check_capability, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission
from app.models.project import Project
from app.models.user_tenant_role import Capability, TenantRole
from app.schemas.dashboard import MeasureOut
from app.schemas.portfolio import (
    PortfolioActivityOut,
    PortfolioMonthActivitiesOut,
    PortfolioMonthOut,
    PortfolioOut,
    PortfolioProjectOut,
    PortfolioSummaryOut,
)
from app.services.analytics import CURRENCY
from app.services.portfolio import (
    ProjectPortfolio,
    ScoredActivity,
    activities_in_month,
    float_days,
    portfolio_months,
    project_portfolio,
    visible_projects,
)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

_TOP_ACTIVITIES = 15
_MONTH_ACTIVITIES = 50


def _require_company(ctx: AuthContext) -> None:
    # A portfolio is company-wide data; a subcontractor only ever sees its scopes.
    if ctx.role == TenantRole.subcontractor:
        raise HTTPException(status_code=403, detail="Not permitted")
    check_capability(ctx, Capability.view_overview)


def _activity_out(p: Project, s: ScoredActivity) -> PortfolioActivityOut:
    a = s.activity
    return PortfolioActivityOut(
        project_id=p.id,
        project_code=p.code,
        id=a.id,
        external_id=a.external_id,
        name=a.name,
        status=a.status.value,
        task_type=a.task_type,
        start=s.start,
        finish=s.finish,
        total_float_days=round(float_days(a), 1) if a.total_float_hours is not None else None,
        criticality_score=s.score,
        criticality_breakdown=s.breakdown,
    )


def _project_out(pp: ProjectPortfolio) -> PortfolioProjectOut:
    return PortfolioProjectOut(
        id=pp.project.id,
        name=pp.project.name,
        code=pp.project.code,
        has_schedule=pp.has_schedule,
        data_date=pp.data_date,
        activity_count=pp.activity_count,
        spi=round(pp.spi, 2) if pp.spi is not None else None,
        planned_pct=pp.planned_pct,
        actual_pct=pp.actual_pct,
        start=pp.start,
        actual_start=pp.actual_start,
        forecast_finish=pp.forecast_finish,
        baseline_finish=pp.baseline_finish,
        finish_variance_days=pp.finish_variance_days,
        quality_score=pp.quality_score,
        progress=pp.progress,
        risk=pp.risk,
        quality=pp.quality,
        critical_count=pp.critical_count,
        negative_float_count=pp.negative_float_count,
        months=[PortfolioMonthOut(**vars(m)) for m in pp.months],
        has_baseline=pp.has_baseline,
        hours=MeasureOut.of(pp.hours) if pp.hours else None,
        cost=MeasureOut.of(pp.cost) if pp.cost else None,
    )


def _summary(projects: list[ProjectPortfolio]) -> PortfolioSummaryOut:
    scheduled = [p for p in projects if p.has_schedule]
    progress = {k: 0 for k in ("ahead", "on_schedule", "slightly_behind", "behind")}
    risk = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    quality = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    overruns = []
    for p in scheduled:
        if p.progress in progress:
            progress[p.progress] += 1
        risk[p.risk] = risk.get(p.risk, 0) + 1
        quality[p.quality] = quality.get(p.quality, 0) + 1
        # Overrun of a behind project: finish slip as a share of its planned span.
        if p.progress == "behind" and p.finish_variance_days is not None and p.start and p.baseline_finish:
            planned_span = (p.baseline_finish - p.start).days
            if planned_span > 0:
                overruns.append(max(0, p.finish_variance_days) / planned_span * 100)
    return PortfolioSummaryOut(
        progress=progress,
        behind_avg_overrun_pct=round(sum(overruns) / len(overruns), 2) if overruns else None,
        risk=risk,
        quality=quality,
    )


@router.get("", response_model=PortfolioOut)
def get_portfolio(db: Session = Depends(get_db), ctx: AuthContext = Depends(get_current_tenant_user)) -> Response:
    _require_company(ctx)
    visible = visible_projects(db, ctx.tenant_id, ctx.user.id, ctx.role)
    # Per user (who sees which projects), invalidated by a change to any of them.
    return cached_json(
        "portfolio",
        scopes=project_scopes(ctx.tenant_id, *(p.id for p in visible)),
        key=[ctx.tenant_id, ctx.user.id],
        compute=lambda: _portfolio(db, ctx, visible),
    )


def _portfolio(db: Session, ctx: AuthContext, visible: list[Project]) -> PortfolioOut:
    projects = [project_portfolio(db, ctx.tenant_id, p) for p in visible]

    top: list[PortfolioActivityOut] = []
    for pp in projects:
        top.extend(_activity_out(pp.project, s) for s in pp.scored if s.score is not None)
    top.sort(key=lambda a: (-(a.criticality_score or 0), a.project_code, a.external_id))

    return PortfolioOut(
        generated_at=datetime.utcnow(),
        currency=CURRENCY,
        projects=[_project_out(pp) for pp in projects],
        months=[PortfolioMonthOut(**vars(m)) for m in portfolio_months(projects)],
        summary=_summary(projects),
        top_activities=top[:_TOP_ACTIVITIES],
    )


@router.get("/projects/{project_id}/months/{month}", response_model=PortfolioMonthActivitiesOut)
def get_month_activities(
    project_id: uuid.UUID,
    month: str = Path(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> PortfolioMonthActivitiesOut:
    """One project's activities active in a month, most critical first — the
    timeline's drill-down."""
    _require_company(ctx)
    project = get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, Capability.view_overview)
    pp = project_portfolio(db, ctx.tenant_id, project)
    in_month = activities_in_month(pp.scored, month)
    return PortfolioMonthActivitiesOut(
        project_id=project.id,
        month=month,
        total=len(in_month),
        activities=[_activity_out(project, s) for s in in_month[:_MONTH_ACTIVITIES]],
    )
