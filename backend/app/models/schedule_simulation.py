import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import Date, DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


class ScheduleSimulation(Base):
    """A saved Schedule Simulation scenario: a simulation data date and the
    hypothetical changes (services/schedule_simulation.py). Only the inputs are
    kept — results are recomputed on demand, because the live programme moves
    on with every update; `last_finish_delta_days` is the last run's headline,
    for the scenario list."""

    __tablename__ = "schedule_simulations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    simulation_data_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # [{external_id, kind, value, actual_start}] — keyed by activity ID, not row
    # id, so a scenario still reads after the next update is imported.
    edits: Mapped[list] = mapped_column(_JSON, nullable=False, default=list)
    # Not a FK (as risk_simulation_runs): the import the scenario last ran on.
    schedule_import_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid(as_uuid=True), nullable=True)
    revision_label: Mapped[str | None] = mapped_column(String(30), nullable=True)
    last_finish_delta_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
