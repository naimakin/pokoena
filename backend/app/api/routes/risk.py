import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission
from app.engine.risk.monte_carlo import ActivityRiskOverride, run_monte_carlo
from app.models.activity import Activity
from app.models.activity_relationship import ActivityRelationship
from app.models.calendar import Calendar
from app.models.project import Project
from app.schemas.risk import MonteCarloRequest, MonteCarloResultOut
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
