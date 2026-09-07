import enum
import uuid
from datetime import date, datetime

import sqlalchemy as sa
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
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


class RiskStatus(str, enum.Enum):
    open = "open"
    mitigating = "mitigating"
    closed = "closed"
    occurred = "occurred"


class MitigationStatus(str, enum.Enum):
    none = "none"
    draft = "draft"
    submitted = "submitted"
    accepted = "accepted"
    needs_revision = "needs_revision"


class MitigationStrategy(str, enum.Enum):
    mitigate = "mitigate"
    avoid = "avoid"
    transfer = "transfer"
    accept = "accept"


class RiskActionStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    done = "done"
    dropped = "dropped"


class RiskItem(Base):
    """One entry in a project's risk register. The row doubles as its own
    mitigation-plan header — probability/impact/score/status is the register +
    matrix data; mitigation_strategy/status/summary + RiskActionItem children
    are the response plan, reviewed by a company_admin (mirrors RecoveryPlan)."""

    __tablename__ = "risk_items"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_risk_items_project_code"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)

    code: Mapped[str] = mapped_column(String(20), nullable=False)  # "R-1", "R-2"… per project
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    effect: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(60), nullable=True)

    probability: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    impact: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=9)
    status: Mapped[RiskStatus] = mapped_column(
        SAEnum(RiskStatus, name="risk_status"), nullable=False, default=RiskStatus.open
    )

    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    wbs_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    activity_external_ids: Mapped[list] = mapped_column(_JSON, nullable=False, default=list)

    mitigation_strategy: Mapped[MitigationStrategy | None] = mapped_column(
        SAEnum(MitigationStrategy, name="mitigation_strategy"), nullable=True
    )
    mitigation_status: Mapped[MitigationStatus] = mapped_column(
        SAEnum(MitigationStatus, name="mitigation_status"), nullable=False, default=MitigationStatus.none
    )
    mitigation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RiskActionItem(Base):
    """One itemised response action under a risk's mitigation plan."""

    __tablename__ = "risk_action_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    risk_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("risk_items.id", ondelete="CASCADE"), nullable=False, index=True
    )

    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[RiskActionStatus] = mapped_column(
        SAEnum(RiskActionStatus, name="risk_action_status"), nullable=False, default=RiskActionStatus.open
    )
    completed_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
