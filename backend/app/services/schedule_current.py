"""Which ScheduleImport is the project's live schedule ("Current update").

Every upload becomes current automatically (see services/xer_import.py); the
user can re-point it from Program Library. Most engines only need the current
import's data date, so they all go through `get_current_import` rather than
"newest by imported_at" — which stops being true once the user re-points it.

Falls back to the newest import when none is flagged (projects whose imports
predate the flag and haven't been touched since, and imports created directly in
tests)."""

from __future__ import annotations

import uuid

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.schedule_import import ScheduleImport


def get_current_import(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID) -> ScheduleImport | None:
    query = db.query(ScheduleImport).filter(ScheduleImport.tenant_id == tenant_id, ScheduleImport.project_id == project_id)
    return query.filter(ScheduleImport.is_current.is_(True)).first() or query.order_by(ScheduleImport.imported_at.desc()).first()


def mark_current(db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID, import_id: uuid.UUID) -> None:
    """Flag `import_id` as the project's current import and clear it everywhere else."""
    db.execute(
        update(ScheduleImport)
        .where(ScheduleImport.tenant_id == tenant_id, ScheduleImport.project_id == project_id)
        .values(is_current=(ScheduleImport.id == import_id))
    )
