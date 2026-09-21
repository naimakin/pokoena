import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Generic JSON everywhere (needed for the SQLite test suite); real JSONB on Postgres.
_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


class ScheduleImport(Base):
    """One row per .xer upload — audit/history, not a full versioned snapshot.
    Records that an import happened; the resulting activities/relationships are
    written straight into the live `activities`/`activity_relationships` tables."""

    __tablename__ = "schedule_imports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    data_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Human sequence label for the Program Library / sync log. Ordinary status
    # updates are numbered per-project ("UPD-1", "UPD-2"…) with revision_no set;
    # the baseline programme (first upload, or any upload via Planning →
    # Baselines) is "Baseline programme" with revision_no NULL — the baseline
    # keeps its own version label and stays out of the UPD sequence.
    revision_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revision_label: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Optional, user-declared: this import is the F9 return of a specific Poko
    # export. Shown as metadata in the sync log ("UPD-5 · from EXP-3"), never
    # part of the identity or the counter.
    roundtrip_from_export_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("schedule_exports.id"), nullable=True
    )
    imported_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    # The import that IS the project's live schedule right now ("Current update"
    # in Program Library). A new upload becomes current automatically; the user can
    # re-point it at any import that still has its source file (`has_source_file`),
    # which rebuilds the live tables from that file. At most one per project
    # (app-enforced — see services/schedule_current.py).
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.false())
    # Gzipped original .xer, kept so the live schedule can be rebuilt exactly from
    # this import later. NULL for uploads made before file storage existed. Deferred:
    # it's megabytes and only the set-current path ever reads it.
    has_source_file: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.false())
    source_file: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    activity_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    critical_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warnings: Mapped[list] = mapped_column(_JSON, nullable=False, default=list)
    # Frozen list of this import's relationships (pred/succ external_id, link
    # type, lag, criticality at import time) — enough for Logic Diff
    # (engine/diff/logic_diff.py) to compare two imports without a full
    # versioned schedule graph. See services/xer_import.py for how it's built.
    relationships_snapshot: Mapped[list] = mapped_column(_JSON, nullable=False, default=list)
    # Frozen per-activity finish dates / criticality / status at import time —
    # the only place a "vs previous UPD" slip comparison can come from, since
    # the live `activities` table is overwritten wholesale on every import.
    # Consumed by engine/diff/slip_diff.py. Built in services/xer_import.py
    # alongside relationships_snapshot.
    activities_snapshot: Mapped[list] = mapped_column(_JSON, nullable=False, default=list)
