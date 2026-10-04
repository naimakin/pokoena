import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission
from app.engine.quality.dcma import DcmaThresholds, run_dcma, validate_thresholds
from app.models.activity import Activity
from app.models.activity_relationship import ActivityRelationship
from app.models.calendar import Calendar
from app.models.project import Project
from app.models.resource_assignment import ResourceAssignment
from app.models.user_tenant_role import EDIT_CAPABLE_PROJECT_ROLES, TenantRole
from app.schemas.dcma import DcmaReportOut
from app.services.schedule_current import get_current_import, to_naive

router = APIRouter(prefix="/projects/{project_id}/dcma", tags=["dcma"])


def _can_edit_thresholds(ctx: AuthContext) -> bool:
    """The project's quality bar is a company call, not a subcontractor's."""
    if ctx.role == TenantRole.company_admin:
        return True
    return ctx.role != TenantRole.subcontractor and bool(set(ctx.project_roles) & EDIT_CAPABLE_PROJECT_ROLES)


@router.get("", response_model=DcmaReportOut)
def get_dcma_report(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> DcmaReportOut:
    project = get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)

    activities = db.query(Activity).filter(Activity.tenant_id == ctx.tenant_id, Activity.project_id == project_id).all()
    activity_ids = [a.id for a in activities]
    relationships = (
        db.query(ActivityRelationship)
        .filter(ActivityRelationship.tenant_id == ctx.tenant_id, ActivityRelationship.project_id == project_id)
        .all()
        if activity_ids
        else []
    )

    calendar = (
        db.query(Calendar).filter(Calendar.tenant_id == ctx.tenant_id, Calendar.project_id == project_id).first()
    )
    hours_per_day = calendar.hours_per_day if calendar else 8.0

    last_import = get_current_import(db, ctx.tenant_id, project_id)
    data_date = to_naive(last_import.data_date) if last_import else None

    assigned_activity_ids = {
        row.activity_id
        for row in db.query(ResourceAssignment.activity_id)
        .filter(ResourceAssignment.tenant_id == ctx.tenant_id, ResourceAssignment.project_id == project_id)
        .all()
    }

    thresholds = DcmaThresholds.from_overrides(project.dcma_thresholds)
    report = run_dcma(activities, relationships, hours_per_day, data_date, assigned_activity_ids, thresholds)
    out = DcmaReportOut.model_validate(report)
    out.default_thresholds = DcmaThresholds().as_dict()
    out.customized = sorted(k for k, v in out.thresholds.items() if out.default_thresholds.get(k) != v)
    out.can_edit_thresholds = _can_edit_thresholds(ctx)
    return out


@router.put("/thresholds")
def set_dcma_thresholds(
    project_id: uuid.UUID,
    body: dict[str, float],
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> dict:
    """The project's own DCMA targets. Send every target to keep; one equal to
    DCMA's default is not stored, so an empty body (or all defaults) goes back
    to DCMA's own targets."""
    project = get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)
    if not _can_edit_thresholds(ctx):
        raise HTTPException(status_code=403, detail="Only a company admin or a project editor can change the targets")
    errors = validate_thresholds(body)
    if errors:
        raise HTTPException(status_code=422, detail={"code": "invalid_thresholds", "message": "Some targets aren't valid.", "errors": errors})
    defaults = DcmaThresholds().as_dict()
    overrides = {k: float(v) for k, v in body.items() if defaults.get(k) != float(v)}
    project.dcma_thresholds = overrides or None
    db.commit()
    return {"thresholds": DcmaThresholds.from_overrides(overrides).as_dict(), "customized": sorted(overrides)}
