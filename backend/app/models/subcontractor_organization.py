import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SubcontractorOrganization(Base):
    """A subcontractor firm within a tenant (e.g. 'MEP Systems Inc.'). Groups the
    individual subcontractor users who work for that firm; access itself is still
    granted per-user via SubcontractorScopeAssignment, not at the firm level."""

    __tablename__ = "subcontractor_organizations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    discipline: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
