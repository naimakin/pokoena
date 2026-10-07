import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission
from app.models.project import Project
from app.models.schedule_import import ScheduleImport
from app.models.user_tenant_role import Capability
from app.schemas.schedule_change import ScheduleChangeReportOut
from app.services.schedule_changes import build_change_report

router = APIRouter(prefix="/projects/{project_id}/schedule-changes", tags=["schedule-changes"])


@router.get("", response_model=ScheduleChangeReportOut)
def get_schedule_changes(
    project_id: uuid.UUID,
    from_import_id: uuid.UUID | None = Query(default=None),
    to_import_id: uuid.UUID | None = Query(default=None),
    date_threshold_days: int = Query(default=1, ge=0, le=60),
    duration_threshold_hours: float = Query(default=8.0, ge=0, le=2000),
    lag_threshold_hours: float = Query(default=8.0, ge=0, le=2000),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> ScheduleChangeReportOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, Capability.view_delivery, Capability.view_reports)

    for import_id in (from_import_id, to_import_id):
        if import_id is None:
            continue
        row = (
            db.query(ScheduleImport)
            .filter(
                ScheduleImport.tenant_id == ctx.tenant_id,
                ScheduleImport.project_id == project_id,
                ScheduleImport.id == import_id,
            )
            .first()
        )
        if row is None:
            raise HTTPException(status_code=400, detail="Unknown schedule import for this project")

    result = build_change_report(
        db,
        ctx.tenant_id,
        project_id,
        from_import_id=from_import_id,
        to_import_id=to_import_id,
        date_threshold_days=date_threshold_days,
        duration_threshold_hours=duration_threshold_hours,
        lag_threshold_hours=lag_threshold_hours,
    )
    return ScheduleChangeReportOut.model_validate(result)
