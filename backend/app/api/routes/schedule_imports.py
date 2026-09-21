import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session, defer

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission
from app.engine.cpm.calendar_engine import NoWorkingDayError
from app.engine.cpm.scheduler import CpmCycleError
from app.models.activity import Activity
from app.models.baseline import Baseline
from app.models.project import Project
from app.models.recovery_plan import RecoveryPlan
from app.models.schedule_export import ScheduleExport
from app.models.schedule_import import ScheduleImport
from app.models.schedule_status_snapshot import ScheduleStatusSnapshot
from app.parser.xer_parser import XerParseError
from app.schemas.activity import ScheduleImportOut, ScheduleImportUpdate
from app.services.xer_import import DataDateRegressionError, import_xer

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
    force: bool = Form(False),
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
            roundtrip_from_export_id=roundtrip_from_export_id, force=force,
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
    except DataDateRegressionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.patch("/{import_id}", response_model=ScheduleImportOut)
def update_schedule_import(
    project_id: uuid.UUID,
    import_id: uuid.UUID,
    payload: ScheduleImportUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> ScheduleImport:
    """Renames an import's revision label (e.g. "UPD-3" → "UPD-3 Mar close-out").
    The UPD sequence itself runs off revision_no, so a rename never disturbs the
    numbering of later uploads."""
    row = get_tenant_scoped_or_404(db, ScheduleImport, import_id, ctx)
    if row.project_id != project_id:
        raise HTTPException(status_code=404, detail="ScheduleImport not found")
    require_project_permission(db, project_id, ctx, need_edit=True)

    label = payload.revision_label.strip()
    if not label:
        raise HTTPException(status_code=400, detail="Revision label can't be blank")
    row.revision_label = label
    # The trend snapshot keeps its own copy of the label (Project Status chart axis).
    db.query(ScheduleStatusSnapshot).filter(ScheduleStatusSnapshot.schedule_import_id == import_id).update(
        {ScheduleStatusSnapshot.revision_label: label}
    )
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{import_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule_import(
    project_id: uuid.UUID,
    import_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> None:
    """Removes a mis-uploaded or no-longer-wanted import from history. Two
    imports can never be deleted: the most recent one (it *is* the live
    schedule — activities/relationships were overwritten wholesale from it,
    see services/xer_import.py) and one a baseline is locked from (baselines
    are a permanent commitment, never silently discarded). Deleting any other
    import also drops its ScheduleStatusSnapshot trend point and clears the
    now-dangling references on activities/recovery plans."""
    row = get_tenant_scoped_or_404(db, ScheduleImport, import_id, ctx)
    if row.project_id != project_id:
        raise HTTPException(status_code=404, detail="ScheduleImport not found")
    require_project_permission(db, project_id, ctx, need_edit=True)

    latest = (
        db.query(ScheduleImport.id)
        .filter(ScheduleImport.tenant_id == ctx.tenant_id, ScheduleImport.project_id == project_id)
        .order_by(ScheduleImport.imported_at.desc())
        .first()
    )
    if latest is not None and latest[0] == import_id:
        raise HTTPException(status_code=409, detail="Can't delete the current schedule — upload a corrected file to replace it")

    baseline_ref = (
        db.query(Baseline.id)
        .filter(Baseline.tenant_id == ctx.tenant_id, Baseline.schedule_import_id == import_id)
        .first()
    )
    if baseline_ref is not None:
        raise HTTPException(status_code=409, detail="This import is locked as a baseline and can't be deleted")

    db.query(ScheduleStatusSnapshot).filter(ScheduleStatusSnapshot.schedule_import_id == import_id).delete()
    db.query(Activity).filter(Activity.last_import_id == import_id).update({Activity.last_import_id: None})
    db.query(RecoveryPlan).filter(RecoveryPlan.from_import_id == import_id).update({RecoveryPlan.from_import_id: None})
    db.query(RecoveryPlan).filter(RecoveryPlan.to_import_id == import_id).update({RecoveryPlan.to_import_id: None})

    db.delete(row)
    db.commit()
