import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum as SAEnum, Float, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProgressEntryType(str, enum.Enum):
    actual = "actual"
    correction = "correction"
    forecast = "forecast"


class ProgressEntry(Base):
    """One activity's daily reported "burned manhours" — the AC (Actual Cost,
    in manhours) input to the S-curve time series once a baseline is active.
    Re-submitting the same (project, activity, entry_date) upserts and marks
    the row `correction` — see api/routes/evm.py::submit_progress. The
    reference project's offline-first `local_uuid` idempotent-sync field is
    dropped — not applicable to this web app."""

    __tablename__ = "progress_entries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    activity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.id"), nullable=False, index=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    burned_manhours_daily: Mapped[float] = mapped_column(Float, nullable=False)
    physical_pct_snapshot: Mapped[float | None] = mapped_column(Float, nullable=True)
    entry_type: Mapped[ProgressEntryType] = mapped_column(
        SAEnum(ProgressEntryType, name="progress_entry_type"), nullable=False, default=ProgressEntryType.actual
    )
    crew_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_out_of_sequence: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
