import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission
from app.engine.export.xer_writer import build_xer
from app.models.activity import Activity
from app.models.activity_code import ActivityCodeType, ActivityCodeValue, TaskActivityCode
from app.models.activity_relationship import ActivityRelationship
from app.models.calendar import Calendar
from app.models.project import Project
from app.models.resource import Resource
from app.models.resource_assignment import ResourceAssignment
from app.models.schedule_export import ScheduleExport
from app.models.wbs_node import WbsNode
from app.services.schedule_current import get_current_import, to_naive

router = APIRouter(prefix="/projects/{project_id}/export", tags=["export"])


@router.get("/xer")
def export_xer(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> Response:
    project = get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)

    activities = db.query(Activity).filter(Activity.tenant_id == ctx.tenant_id, Activity.project_id == project_id).all()
    relationships = (
        db.query(ActivityRelationship)
        .filter(ActivityRelationship.tenant_id == ctx.tenant_id, ActivityRelationship.project_id == project_id)
        .all()
    )
    calendars = db.query(Calendar).filter(Calendar.tenant_id == ctx.tenant_id, Calendar.project_id == project_id).all()
    wbs_nodes = db.query(WbsNode).filter(WbsNode.tenant_id == ctx.tenant_id, WbsNode.project_id == project_id).all()
    resources = db.query(Resource).filter(Resource.tenant_id == ctx.tenant_id, Resource.project_id == project_id).all()
    assignments = (
        db.query(ResourceAssignment)
        .filter(ResourceAssignment.tenant_id == ctx.tenant_id, ResourceAssignment.project_id == project_id)
        .all()
    )
    code_types = (
        db.query(ActivityCodeType)
        .filter(ActivityCodeType.tenant_id == ctx.tenant_id, ActivityCodeType.project_id == project_id)
        .all()
    )
    code_values = (
        db.query(ActivityCodeValue)
        .filter(ActivityCodeValue.tenant_id == ctx.tenant_id, ActivityCodeValue.project_id == project_id)
        .all()
    )
    task_activity_codes = (
        db.query(TaskActivityCode)
        .filter(TaskActivityCode.tenant_id == ctx.tenant_id, TaskActivityCode.project_id == project_id)
        .all()
    )

    last_import = get_current_import(db, ctx.tenant_id, project_id)
    data_date = to_naive(last_import.data_date) if last_import else None

    xer_bytes = build_xer(
        project, activities, relationships, calendars, wbs_nodes, resources, assignments,
        code_types, code_values, task_activity_codes, data_date,
    )

    # Log the export with a per-project sequence label (EXP-1, EXP-2…) so the
    # user can tell which file they sent to P6 and which F9 result came back.
    next_no = (
        db.query(func.max(ScheduleExport.revision_no))
        .filter(ScheduleExport.tenant_id == ctx.tenant_id, ScheduleExport.project_id == project_id)
        .scalar()
        or 0
    ) + 1
    filename = f"{project.code}-EXP-{next_no}.xer"
    db.add(
        ScheduleExport(
            tenant_id=ctx.tenant_id,
            project_id=project_id,
            revision_no=next_no,
            revision_label=f"EXP-{next_no}",
            source_filename=filename,
            data_date=data_date,
            activity_count=len(activities),
            exported_by_user_id=ctx.user.id,
        )
    )
    db.commit()

    return Response(
        content=xer_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
