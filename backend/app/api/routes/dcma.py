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
from app.models.schedule_import import ScheduleImport
from app.schemas.dcma import DcmaReportOut

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

    last_import = (
        db.query(ScheduleImport)
        .filter(ScheduleImport.tenant_id == ctx.tenant_id, ScheduleImport.project_id == project_id)
        .order_by(ScheduleImport.imported_at.desc())
        .first()
    )
    data_date = last_import.data_date if last_import else None

    report = run_dcma(activities, relationships, hours_per_day, data_date)
    return DcmaReportOut.model_validate(report)
