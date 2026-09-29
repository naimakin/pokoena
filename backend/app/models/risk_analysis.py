import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


class RiskAnalysisSettings(Base):
    """One row per project: how its QSRA runs (engine/risk/qsra.py).

    `confidence` picks the background-uncertainty range every remaining
    activity gets (see services/risk_analysis.py::CONFIDENCE_RANGES). The seed
    is fixed per project on purpose: two runs with the same inputs give the same
    answer, so a movement between runs is a movement in the project, not noise."""

    __tablename__ = "risk_analysis_settings"
    __table_args__ = (UniqueConstraint("project_id", name="uq_risk_analysis_settings_project"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    confidence: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    seed: Mapped[int] = mapped_column(Integer, nullable=False, default=20260929)
    # Contract / committed finish to measure P(on time) against; falls back to
    # the baseline finish when empty.
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Measure this milestone instead of the last activity to finish.
    finish_activity_external_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    near_critical_days: Mapped[float] = mapped_column(Float, nullable=False, default=10.0)
    correlate_by_wbs: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RiskSimulationRun(Base):
    """One QSRA run with a frozen copy of what went into it (risks, settings,
    data date) and everything it produced. Kept, not overwritten: the P-dates
    and probability of finishing on time across runs are the confidence trend."""

    __tablename__ = "risk_simulation_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    # Deliberately not a FK — a run outlives the import it was made on (see
    # migration 0027), and keeps its own copy of the label and data date.
    schedule_import_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid(as_uuid=True), nullable=True)
    revision_label: Mapped[str | None] = mapped_column(String(30), nullable=True)
    data_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    iterations: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    settings: Mapped[dict] = mapped_column(_JSON, nullable=False, default=dict)
    inputs: Mapped[dict] = mapped_column(_JSON, nullable=False, default=dict)
    results: Mapped[dict] = mapped_column(_JSON, nullable=False, default=dict)
    ranking: Mapped[list | None] = mapped_column(_JSON, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
