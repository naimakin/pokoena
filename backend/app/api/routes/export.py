import gzip
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission
from app.engine.export.xer_progress import rewrite_progress
from app.engine.export.xer_writer import build_xer
from app.models.activity import Activity
from app.models.activity_code import ActivityCodeType, ActivityCodeValue, TaskActivityCode
from app.models.activity_relationship import ActivityRelationship
from app.models.calendar import Calendar
from app.models.project import Project
from app.models.resource import Resource
from app.models.resource_assignment import ResourceAssignment
from app.models.schedule_export import ScheduleExport
from app.models.schedule_import import ScheduleImport
from app.models.wbs_node import WbsNode
from app.models.user_tenant_role import Capability
from app.services.schedule_current import get_current_import, to_naive

router = APIRouter(prefix="/projects/{project_id}/export", tags=["export"])


def _resolve_source_import(
    db: Session, ctx: AuthContext, project_id: uuid.UUID, import_id: uuid.UUID | None
) -> ScheduleImport | None:
    """Which programme this export is built from. No `import_id` means the
    current update — the schedule every other page shows — which is what the
    export page defaults to. Any other import is exported from its own stored
    .xer, so one that never had a file can only be exported while it IS the
    current update (the synthesized fallback below is built off the live
    tables, which are that import's)."""
    if import_id is None:
        return get_current_import(db, ctx.tenant_id, project_id)

    row = get_tenant_scoped_or_404(db, ScheduleImport, import_id, ctx)
    if row.project_id != project_id:
        raise HTTPException(status_code=404, detail="ScheduleImport not found")

    if not row.has_source_file:
        current = get_current_import(db, ctx.tenant_id, project_id)
        if current is None or current.id != row.id:
            raise HTTPException(
                status_code=400,
                detail="This programme was uploaded before Poko kept the original .xer file, so it can't be exported. Pick another programme.",
            )
    return row


@router.get("/xer")
def export_xer(
    project_id: uuid.UUID,
    import_id: uuid.UUID | None = Query(None, description="Programme to export; defaults to the current update"),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> Response:
    project = get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, Capability.export)

    source_import = _resolve_source_import(db, ctx, project_id, import_id)
    data_date = to_naive(source_import.data_date) if source_import else None

    activities = db.query(Activity).filter(Activity.tenant_id == ctx.tenant_id, Activity.project_id == project_id).all()

    # Preferred path: hand back the file P6 itself produced, with Poko's
    # progress written into it. Synthesizing a .xer from our own tables can't
    # produce something P6 will import — see engine/export/xer_progress.py.
    # Progress is matched on task_code, so exporting an earlier programme
    # carries Poko's progress onto the activities it shares with the live
    # schedule and leaves the rest of its file as P6 wrote it.
    if source_import is not None and source_import.has_source_file and source_import.source_file:
        xer_bytes, task_rows, _patched = rewrite_progress(
            gzip.decompress(source_import.source_file), activities
        )
        return _respond(db, ctx, project, project_id, xer_bytes, task_rows, data_date, source_import)

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

    xer_bytes = build_xer(
        project, activities, relationships, calendars, wbs_nodes, resources, assignments,
        code_types, code_values, task_activity_codes, data_date,
    )
    return _respond(db, ctx, project, project_id, xer_bytes, len(activities), data_date, source_import)


def _respond(db, ctx, project, project_id, xer_bytes, activity_count, data_date, source_import) -> Response:
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
            source_import_id=source_import.id if source_import is not None else None,
            activity_count=activity_count,
            exported_by_user_id=ctx.user.id,
        )
    )
    db.commit()

    return Response(
        content=xer_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
