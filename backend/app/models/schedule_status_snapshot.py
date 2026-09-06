import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ScheduleStatusSnapshot(Base):
    """The project-status rollup frozen at one .xer import — SPI / DCMA quality
    score / schedule-recovery index / % complete, plus the three headline
    verdicts. One row per import (see services/xer_import.py's write hook), so
    the Execution → Project Status page can trend these across UPD-1, UPD-2…

    The live schedule tables (activities/relationships) are overwritten on every
    import and keep no history, so this is the only place a per-version status
    trend can come from. The status route also synthesises a live "current"
    point when the latest import predates this table, so a chart always has at
    least one point."""

    __tablename__ = "schedule_status_snapshots"
    __table_args__ = (
        UniqueConstraint("schedule_import_id", name="uq_schedule_status_snapshots_import"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    schedule_import_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedule_imports.id"), nullable=False
    )

    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    data_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Copied from the import so the trend chart's x-axis label is stable even if
    # the import is later renumbered.
    revision_label: Mapped[str | None] = mapped_column(String(30), nullable=True)

    spi: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpi: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Remaining critical-path work ÷ working time left to the baseline finish,
    # normalised so 1.0 = on pace. A header estimate (nominal 8h/day, 5d/wk) —
    # not a substitute for the EVM engine's TCPI.
    schedule_recovery_index: Mapped[float | None] = mapped_column(Float, nullable=True)

    dcma_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    dcma_status: Mapped[str | None] = mapped_column(String(10), nullable=True)

    activity_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    critical_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    negative_float_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overdue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    percent_complete: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    progress_verdict: Mapped[str | None] = mapped_column(String(20), nullable=True)
    risk_verdict: Mapped[str | None] = mapped_column(String(20), nullable=True)
    quality_verdict: Mapped[str | None] = mapped_column(String(20), nullable=True)
