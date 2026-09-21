import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission
from app.engine.quality.dcma import run_dcma
from app.models.activity import Activity
from app.models.activity_relationship import ActivityRelationship
from app.models.calendar import Calendar
from app.models.project import Project
from app.models.resource_assignment import ResourceAssignment
from app.schemas.dcma import DcmaReportOut
from app.services.schedule_current import get_current_import

router = APIRouter(prefix="/projects/{project_id}/dcma", tags=["dcma"])


@router.get("", response_model=DcmaReportOut)
def get_dcma_report(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> DcmaReportOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
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
    data_date = last_import.data_date if last_import else None

    assigned_activity_ids = {
        row.activity_id
        for row in db.query(ResourceAssignment.activity_id)
        .filter(ResourceAssignment.tenant_id == ctx.tenant_id, ResourceAssignment.project_id == project_id)
        .all()
    }

    report = run_dcma(activities, relationships, hours_per_day, data_date, assigned_activity_ids)
    return DcmaReportOut.model_validate(report)
