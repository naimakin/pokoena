import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EvmSnapshot(Base):
    """One date's point on a baseline's EVM time series — PV/EV/AC plus the
    derived indices (SPI/CPI/EAC/ETC/TCPI). Recomputed synchronously whenever
    new progress entries land (see api/routes/evm.py::submit_progress and
    engine/evm/scurve_engine.py::compute_evm_series) — the reference project
    does this as a FastAPI background task; at our scale it's fast enough to
    do inline, same simplification already made for Monte Carlo and DCMA."""

    __tablename__ = "evm_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    baseline_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("baselines.id"), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    pv_cumulative: Mapped[float | None] = mapped_column(Float, nullable=True)
    ev_cumulative: Mapped[float | None] = mapped_column(Float, nullable=True)
    ac_cumulative: Mapped[float | None] = mapped_column(Float, nullable=True)
    spi: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpi: Mapped[float | None] = mapped_column(Float, nullable=True)
    sv: Mapped[float | None] = mapped_column(Float, nullable=True)
    cv: Mapped[float | None] = mapped_column(Float, nullable=True)
    bac: Mapped[float | None] = mapped_column(Float, nullable=True)
    eac: Mapped[float | None] = mapped_column(Float, nullable=True)
    etc: Mapped[float | None] = mapped_column(Float, nullable=True)
    tcpi: Mapped[float | None] = mapped_column(Float, nullable=True)
    percent_complete_planned: Mapped[float | None] = mapped_column(Float, nullable=True)
    percent_complete_earned: Mapped[float | None] = mapped_column(Float, nullable=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
