import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ScheduleExport(Base):
    """One row per `.xer` download from Export / Sync to P6 — the counterpart to
    `ScheduleImport`. Gives every exported file a stable, human sequence label
    (``EXP-1``, ``EXP-2``…) so a user can tell which file they sent to Primavera
    and which F9 result came back. Independent per-project counter from the
    import side's ``UPD-n``."""

    __tablename__ = "schedule_exports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    # Per-project sequential (1-based), and its rendered label, e.g. "EXP-3".
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    revision_label: Mapped[str] = mapped_column(String(30), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    data_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The programme this file was built from — the user picks one on Export /
    # Sync to P6, defaulting to the current update. NULL on a project with no
    # imports at all, and on exports made before the picker shipped.
    source_import_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("schedule_imports.id"), nullable=True
    )
    activity_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    exported_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    exported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
