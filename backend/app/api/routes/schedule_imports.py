import gzip
import uuid
from contextlib import contextmanager
from datetime import datetime, time, timezone

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
from app.services.schedule_current import get_current_import
from app.services.xer_import import DataDateRegressionError, import_xer

router = APIRouter(prefix="/projects/{project_id}/schedule-imports", tags=["schedule-imports"])


@contextmanager
def _import_errors():
    """Maps everything import_xer can raise for a bad/unschedulable file onto the
    HTTP errors the upload and set-current endpoints share."""
    try:
        yield
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
    with _import_errors():
        return import_xer(
            db, project_id, ctx, file.filename, file_bytes,
            roundtrip_from_export_id=roundtrip_from_export_id, force=force,
        )


@router.patch("/{import_id}", response_model=ScheduleImportOut)
def update_schedule_import(
    project_id: uuid.UUID,
    import_id: uuid.UUID,
    payload: ScheduleImportUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> ScheduleImport:
    """Edits an import's metadata: its revision label (e.g. "UPD-3" → "UPD-3 Mar
    close-out") and/or its data date. The UPD sequence runs off revision_no, so a
    rename never disturbs the numbering of later uploads.

    Changing the data date only re-labels the moment the schedule is "as of":
    EVM, DCMA, Monte Carlo and export read it live, but the CPM dates/float stored
    from the .xer are NOT recomputed — re-upload the file for that."""
    row = get_tenant_scoped_or_404(db, ScheduleImport, import_id, ctx)
    if row.project_id != project_id:
        raise HTTPException(status_code=404, detail="ScheduleImport not found")
    require_project_permission(db, project_id, ctx, need_edit=True)

    if payload.revision_label is None and payload.data_date is None:
        raise HTTPException(status_code=422, detail="Nothing to update — send a revision label and/or a data date")

    snapshot_changes: dict = {}
    if payload.revision_label is not None:
        label = payload.revision_label.strip()
        if not label:
            raise HTTPException(status_code=400, detail="Revision label can't be blank")
        row.revision_label = label
        snapshot_changes[ScheduleStatusSnapshot.revision_label] = label
    if payload.data_date is not None:
        # Keep the time-of-day (and zone) P6 stamped on the original data date.
        old = row.data_date
        row.data_date = datetime.combine(
            payload.data_date, old.timetz() if old is not None else time(0, tzinfo=timezone.utc)
        )
        snapshot_changes[ScheduleStatusSnapshot.data_date] = row.data_date

    # The status-trend snapshot keeps its own copy of both (Project Status chart).
    db.query(ScheduleStatusSnapshot).filter(ScheduleStatusSnapshot.schedule_import_id == import_id).update(
        snapshot_changes
    )
    db.commit()
    db.refresh(row)
    return row


@router.post("/{import_id}/set-current", response_model=ScheduleImportOut)
def set_current_import(
    project_id: uuid.UUID,
    import_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> ScheduleImport:
    """Makes an earlier import the project's "Current update" by rebuilding the
    live schedule from its stored .xer (dates, float, critical path, relationships,
    resources — exactly as if it had just been uploaded, minus the regression
    check since the user chose it). Progress the company/subcontractors entered
    on matching activities is kept, same as any re-import. Only imports uploaded
    after file storage shipped carry their .xer."""
    row = get_tenant_scoped_or_404(db, ScheduleImport, import_id, ctx)
    if row.project_id != project_id:
        raise HTTPException(status_code=404, detail="ScheduleImport not found")
    require_project_permission(db, project_id, ctx, need_edit=True)

    current = get_current_import(db, ctx.tenant_id, project_id)
    if current is not None and current.id == import_id:
        return row
    if not row.has_source_file or row.source_file is None:
        raise HTTPException(
            status_code=409,
            detail="This import was uploaded before file storage existed, so its schedule can't be restored. "
            "Upload the .xer again to make it the current update.",
        )

    with _import_errors():
        return import_xer(
            db, project_id, ctx, row.filename, gzip.decompress(row.source_file), reuse_import=row
        )


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

    current = get_current_import(db, ctx.tenant_id, project_id)
    if current is not None and current.id == import_id:
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
