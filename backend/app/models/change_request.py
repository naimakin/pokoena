import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RiskLevel(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class ChangeRequestStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ChangeRequest(Base):
    __tablename__ = "change_requests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    update_period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("update_periods.id"), nullable=False, index=True
    )
    activity_relationship_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("activity_relationships.id"), nullable=True
    )
    activity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("activities.id"), nullable=True)
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    field_changed: Mapped[str] = mapped_column(String(120), nullable=False)
    before_value: Mapped[str] = mapped_column(String(255), nullable=False)
    after_value: Mapped[str] = mapped_column(String(255), nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[RiskLevel] = mapped_column(
        SAEnum(RiskLevel, name="risk_level"), nullable=False, default=RiskLevel.medium
    )
    status: Mapped[ChangeRequestStatus] = mapped_column(
        SAEnum(ChangeRequestStatus, name="change_request_status"),
        nullable=False,
        default=ChangeRequestStatus.pending,
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
