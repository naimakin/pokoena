import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum as SAEnum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BaselineStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    superseded = "superseded"


class Baseline(Base):
    """A locked Performance Measurement Baseline — freezes one ScheduleImport's
    activities as "the plan" so later progress (progress_entries) can be
    measured against it over time. Ported from the reference project's
    "Vance Baseline Mandate": at most one `active` baseline per project at a
    time (enforced in app/api/routes/evm.py, not a DB trigger — see that
    module's docstring for why). `total_budget_manhours` (BAC) comes from
    each locked activity's `target_duration_hours`, not resource quantities —
    see engine/evm/scurve_engine.py for why that's a deliberate choice, not
    a simplification."""

    __tablename__ = "baselines"
    __table_args__ = ()

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    schedule_import_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schedule_imports.id"), nullable=False)
    version_label: Mapped[str] = mapped_column(String(120), nullable=False, default="Target-1")
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    total_budget_manhours: Mapped[float] = mapped_column(Float, nullable=False)
    target_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    target_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    distribution_method: Mapped[str] = mapped_column(String(30), nullable=False, default="linear")
    status: Mapped[BaselineStatus] = mapped_column(
        SAEnum(BaselineStatus, name="baseline_status"), nullable=False, default=BaselineStatus.draft
    )
    activity_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BaselineActivity(Base):
    """One activity's frozen planned-manhours/dates at the moment its
    baseline was locked — immutable in practice because the only mutating
    baseline routes are lock (create) and supersede (status flip), never an
    update to these rows."""

    __tablename__ = "baseline_activities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    baseline_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("baselines.id"), nullable=False, index=True)
    activity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.id"), nullable=False)
    planned_manhours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    baseline_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    baseline_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    wbs_code: Mapped[str | None] = mapped_column(String(50), nullable=True)


class BaselinePvCurve(Base):
    """One day's planned-value point on a baseline's time-phased PV curve —
    generated once at lock time by linearly distributing each activity's
    planned_manhours across its baseline_start..baseline_end span. See
    engine/evm/scurve_engine.py::generate_pv_curve."""

    __tablename__ = "baseline_pv_curve"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    baseline_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("baselines.id"), nullable=False, index=True)
    curve_date: Mapped[date] = mapped_column(Date, nullable=False)
    pv_daily: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pv_cumulative: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class BaselineResource(Base):
    """A P6 resource (RSRC) frozen against a baseline at lock time — a copy of
    the live `resources` row so "the resources that were in the BSL programme"
    survives every later update-programme (.xer) import, which replaces the
    live `resources`/`resource_assignments` rows wholesale. Same
    lock-then-supersede immutability as BaselineActivity."""

    __tablename__ = "baseline_resources"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    baseline_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("baselines.id"), nullable=False, index=True)
    rsrc_id: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    rsrc_type: Mapped[str] = mapped_column(String(30), nullable=False, default="RT_Labor")
    unit_id: Mapped[str | None] = mapped_column(String(50), nullable=True)


class BaselineResourceAssignment(Base):
    """One (activity, resource) budget line frozen against a baseline — the
    TASKRSRC `target_qty`/`target_cost` at lock time. Feeds the Baselines
    page's "resources in this baseline" summary and, later, a resource-loaded
    PV curve."""

    __tablename__ = "baseline_resource_assignments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    baseline_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("baselines.id"), nullable=False, index=True)
    activity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.id"), nullable=False)
    baseline_resource_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("baseline_resources.id"), nullable=False)
    target_qty: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    target_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unit_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
