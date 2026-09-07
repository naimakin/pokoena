import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session, defer

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission
from app.engine.cpm.calendar_engine import NoWorkingDayError
from app.engine.cpm.scheduler import CpmCycleError
from app.models.project import Project
from app.models.schedule_export import ScheduleExport
from app.models.schedule_import import ScheduleImport
from app.parser.xer_parser import XerParseError
from app.schemas.activity import ScheduleImportOut
from app.services.xer_import import import_xer

router = APIRouter(prefix="/projects/{project_id}/schedule-imports", tags=["schedule-imports"])


@router.get("", response_model=list[ScheduleImportOut])
def list_schedule_imports(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> list[ScheduleImport]:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)
    return (
        db.query(ScheduleImport)
        # The two frozen snapshots are fat JSONB and never serialized by
        # ScheduleImportOut — don't pull them into memory for the sync-log list.
        .options(
            defer(ScheduleImport.relationships_snapshot),
            defer(ScheduleImport.activities_snapshot),
        )
        .filter(ScheduleImport.tenant_id == ctx.tenant_id, ScheduleImport.project_id == project_id)
        .order_by(ScheduleImport.imported_at.desc())
        .all()
    )


@router.post("", response_model=ScheduleImportOut, status_code=status.HTTP_201_CREATED)
def upload_schedule(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    roundtrip_from_export_id: uuid.UUID | None = Form(None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> ScheduleImport:
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx, need_edit=True)

    if not file.filename or not file.filename.lower().endswith(".xer"):
        raise HTTPException(status_code=400, detail="Only .xer files are supported")

    if roundtrip_from_export_id is not None:
        linked = (
            db.query(ScheduleExport)
            .filter(
                ScheduleExport.tenant_id == ctx.tenant_id,
                ScheduleExport.project_id == project_id,
                ScheduleExport.id == roundtrip_from_export_id,
            )
            .first()
        )
        if linked is None:
            raise HTTPException(status_code=400, detail="Unknown export to link this upload to")

    file_bytes = file.file.read()
    try:
        return import_xer(
            db, project_id, ctx, file.filename, file_bytes,
            roundtrip_from_export_id=roundtrip_from_export_id,
        )
    except XerParseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except CpmCycleError as e:
        raise HTTPException(
            status_code=400,
            detail=f"This schedule can't be recomputed: {e} Fix the circular dependency in P6 and re-export.",
        )
    except NoWorkingDayError as e:
        raise HTTPException(status_code=400, detail=f"This schedule can't be recomputed: {e}")
