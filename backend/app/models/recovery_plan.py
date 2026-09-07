import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RecoveryPlanStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    accepted = "accepted"
    needs_revision = "needs_revision"


class RecoveryItemStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    done = "done"
    dropped = "dropped"


class RecoveryPlan(Base):
    """One recovery plan per slipped activity (Execution → Recovery Plan). The
    responsible party authors it — the subcontractor whose scope the activity is
    in, else a company user for self-perform work — and a company_admin reviews
    (accept / needs_revision), mirroring ChangeRequest. Evergreen per activity:
    if the activity slips again in a later UPD the same plan is revised rather
    than replaced.

    Keyed on `activity_external_id` (the P6 task_code) rather than the activity
    UUID because that key survives a schedule re-import — same reasoning as
    ScheduleImport.relationships_snapshot. `xer_import.py` re-links this column
    when P6 renames an activity."""

    __tablename__ = "recovery_plans"
    __table_args__ = (
        UniqueConstraint("project_id", "activity_external_id", name="uq_recovery_plans_project_activity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)

    activity_external_id: Mapped[str] = mapped_column(String(50), nullable=False)
    p6_task_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    activity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("activities.id", ondelete="SET NULL"), nullable=True
    )
    activity_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    wbs_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Set when a subcontractor authors the plan — the scope gate for their edits.
    project_scope_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_scopes.id"), nullable=True
    )

    origin_update_period_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("update_periods.id"), nullable=True
    )
    from_import_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("schedule_imports.id"), nullable=True)
    to_import_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("schedule_imports.id"), nullable=True)
    slip_days_at_creation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slip_days_at_review: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[RecoveryPlanStatus] = mapped_column(
        SAEnum(RecoveryPlanStatus, name="recovery_plan_status"),
        nullable=False,
        default=RecoveryPlanStatus.draft,
    )
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RecoveryPlanItem(Base):
    """One itemised action in a recovery plan. `project_id` is denormalised so
    tenant-scoped queries and the RLS policy don't have to join through the
    parent plan."""

    __tablename__ = "recovery_plan_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    recovery_plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recovery_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )

    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[RecoveryItemStatus] = mapped_column(
        SAEnum(RecoveryItemStatus, name="recovery_item_status"),
        nullable=False,
        default=RecoveryItemStatus.open,
    )
    completed_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
