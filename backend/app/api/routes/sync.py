import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AuthContext, get_current_tenant_user, get_tenant_scoped_or_404, require_project_permission
from app.models.project import Project
from app.models.schedule_export import ScheduleExport
from app.models.schedule_import import ScheduleImport
from app.models.user import User
from app.schemas.sync import ScheduleExportOut, ScheduleExportUpdate, SyncLogEntry

router = APIRouter(prefix="/projects/{project_id}", tags=["sync"])


@router.get("/sync-log", response_model=list[SyncLogEntry])
def get_sync_log(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> list[SyncLogEntry]:
    """Combined Export / Sync to P6 timeline — every .xer exported (EXP-n) and
    imported (UPD-n / Baseline programme) for this project, newest first."""
    get_tenant_scoped_or_404(db, Project, project_id, ctx)
    require_project_permission(db, project_id, ctx)

    exports = (
        db.query(ScheduleExport)
        .filter(ScheduleExport.tenant_id == ctx.tenant_id, ScheduleExport.project_id == project_id)
        .order_by(ScheduleExport.revision_no.desc())
        .all()
    )
    imports = (
        db.query(ScheduleImport)
        .filter(ScheduleImport.tenant_id == ctx.tenant_id, ScheduleImport.project_id == project_id)
        .order_by(ScheduleImport.imported_at.desc(), ScheduleImport.id.desc())
        .all()
    )
    export_label_by_id = {e.id: e.revision_label for e in exports}

    user_ids = {e.exported_by_user_id for e in exports} | {i.imported_by_user_id for i in imports}
    name_by_user_id = {
        u.id: (u.full_name or u.email)
        for u in db.query(User).filter(User.id.in_(user_ids)).all()
    } if user_ids else {}

    entries = [
        SyncLogEntry(
            kind="export",
            id=e.id,
            label=e.revision_label,
            at=e.exported_at,
            user_id=e.exported_by_user_id,
            user_name=name_by_user_id.get(e.exported_by_user_id),
            activity_count=e.activity_count,
            data_date=e.data_date,
            filename=e.source_filename,
        )
        for e in exports
    ]
    entries += [
        SyncLogEntry(
            kind="import",
            id=i.id,
            label=i.revision_label or "Import",
            at=i.imported_at,
            user_id=i.imported_by_user_id,
            user_name=name_by_user_id.get(i.imported_by_user_id),
            activity_count=i.activity_count,
            data_date=i.data_date,
            filename=i.filename,
            linked_export_label=export_label_by_id.get(i.roundtrip_from_export_id),
        )
        for i in imports
    ]
    # Newest first. Same-instant events (rapid exports/imports in tests, or a
    # tight round-trip) keep a stable order: imports ahead of exports, then by
    # the per-source ordering above.
    entries.sort(key=lambda e: (e.at, 1 if e.kind == "import" else 0), reverse=True)
    return entries


def _get_export(db: Session, project_id: uuid.UUID, export_id: uuid.UUID, ctx: AuthContext) -> ScheduleExport:
    row = get_tenant_scoped_or_404(db, ScheduleExport, export_id, ctx)
    if row.project_id != project_id:
        raise HTTPException(status_code=404, detail="ScheduleExport not found")
    require_project_permission(db, project_id, ctx, need_edit=True)
    return row


@router.patch("/exports/{export_id}", response_model=ScheduleExportOut)
def update_schedule_export(
    project_id: uuid.UUID,
    export_id: uuid.UUID,
    payload: ScheduleExportUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> ScheduleExport:
    """Renames an export in the sync log (e.g. "EXP-2" → "EXP-2 sent to ENKA").
    The EXP sequence runs off revision_no, so later exports keep their numbers.
    Imports have the same endpoint on routes/schedule_imports.py."""
    row = _get_export(db, project_id, export_id, ctx)
    label = payload.revision_label.strip()
    if not label:
        raise HTTPException(status_code=400, detail="Revision label can't be blank")
    row.revision_label = label
    db.commit()
    db.refresh(row)
    return row


@router.delete("/exports/{export_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule_export(
    project_id: uuid.UUID,
    export_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_current_tenant_user),
) -> None:
    """Removes an export from the sync log. Unlike an import, an export owns no
    schedule data — the file was handed to the user and nothing in Poko is
    derived from it — so the only thing to tidy up is the round-trip link on any
    import that was matched back to it, which becomes an unlinked import."""
    row = _get_export(db, project_id, export_id, ctx)

    db.query(ScheduleImport).filter(
        ScheduleImport.tenant_id == ctx.tenant_id,
        ScheduleImport.roundtrip_from_export_id == export_id,
    ).update({ScheduleImport.roundtrip_from_export_id: None}, synchronize_session=False)

    db.delete(row)
    db.commit()
