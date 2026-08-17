import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission
from app.engine.diff.logic_diff import DEFAULT_LAG_THRESHOLD_HOURS, compare_relationship_snapshots
from app.models.project import Project
from app.models.schedule_import import ScheduleImport
from app.schemas.logic_diff import LogicDiffReportOut

router = APIRouter(prefix="/projects/{project_id}/logic-diff", tags=["logic-diff"])


@router.get("", response_model=LogicDiffReportOut)
def get_logic_diff(
    project_id: uuid.UUID,
    from_import_id: uuid.UUID,
    to_import_id: uuid.UUID,
    lag_threshold_hours: float = DEFAULT_LAG_THRESHOLD_HOURS,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> LogicDiffReportOut:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)

    from_import = get_tenant_scoped_or_404(db, ScheduleImport, from_import_id, ctx)
    to_import = get_tenant_scoped_or_404(db, ScheduleImport, to_import_id, ctx)
    if from_import.project_id != project_id or to_import.project_id != project_id:
        raise HTTPException(status_code=400, detail="Both imports must belong to this project")

    summary, changes = compare_relationship_snapshots(
        from_import.relationships_snapshot, to_import.relationships_snapshot, lag_threshold_hours
    )

    return LogicDiffReportOut(
        from_import_id=str(from_import_id),
        to_import_id=str(to_import_id),
        summary=summary,
        changes=changes,
    )
