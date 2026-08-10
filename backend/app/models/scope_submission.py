import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ScopeSubmission(Base):
    """One row per (update_period, company) once that company hits 'Submit My Updates'."""

    __tablename__ = "scope_submissions"
    __table_args__ = (
        UniqueConstraint("update_period_id", "company_id", name="uq_scope_submission_period_company"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    update_period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("update_periods.id"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    submitted_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
