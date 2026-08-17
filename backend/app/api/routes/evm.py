import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission
from app.engine.evm.evm_engine import calculate_evm
from app.models.activity import Activity
from app.models.calendar import Calendar
from app.models.project import Project
from app.models.resource_assignment import ResourceAssignment
from app.models.schedule_import import ScheduleImport
from app.schemas.evm import QuickEvmOut

router = APIRouter(prefix="/projects/{project_id}/evm", tags=["evm"])


@router.get("/quick", response_model=QuickEvmOut)
def get_quick_evm(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> QuickEvmOut:
    """Live EVM computed from the project's current schedule and resource
    assignments — no baseline required. See engine/evm/evm_engine.py."""
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)

    activities = db.query(Activity).filter(Activity.tenant_id == ctx.tenant_id, Activity.project_id == project_id).all()
    assignments = (
        db.query(ResourceAssignment)
        .filter(ResourceAssignment.tenant_id == ctx.tenant_id, ResourceAssignment.project_id == project_id)
        .all()
    )
    calendars = db.query(Calendar).filter(Calendar.tenant_id == ctx.tenant_id, Calendar.project_id == project_id).all()

    last_import = (
        db.query(ScheduleImport)
        .filter(ScheduleImport.tenant_id == ctx.tenant_id, ScheduleImport.project_id == project_id)
        .order_by(ScheduleImport.imported_at.desc())
        .first()
    )
    data_date = last_import.data_date if last_import else None

    result = calculate_evm(activities, assignments, calendars, data_date)
    return QuickEvmOut.model_validate(result)
