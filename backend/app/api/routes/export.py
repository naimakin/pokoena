import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission
from app.engine.export.xer_writer import build_xer
from app.models.activity import Activity
from app.models.activity_relationship import ActivityRelationship
from app.models.calendar import Calendar
from app.models.project import Project
from app.models.resource import Resource
from app.models.resource_assignment import ResourceAssignment
from app.models.schedule_import import ScheduleImport
from app.models.wbs_node import WbsNode

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

    last_import = (
        db.query(ScheduleImport)
        .filter(ScheduleImport.tenant_id == ctx.tenant_id, ScheduleImport.project_id == project_id)
        .order_by(ScheduleImport.imported_at.desc())
        .first()
    )
    data_date = last_import.data_date if last_import else None

    xer_bytes = build_xer(project, activities, relationships, calendars, wbs_nodes, resources, assignments, data_date)

    return Response(
        content=xer_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{project.code}.xer"'},
    )
