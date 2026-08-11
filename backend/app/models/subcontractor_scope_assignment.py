import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SubcontractorScopeAssignment(Base):
    """Grants a subcontractor user access to one project scope. A subcontractor's
    total access is the union of these rows — possibly spanning several projects,
    never anything outside the scopes explicitly assigned here."""

    __tablename__ = "subcontractor_scope_assignments"
    __table_args__ = (
        UniqueConstraint("user_id", "project_scope_id", name="uq_sub_scope_assignment_user_scope"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    project_scope_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_scopes.id"), nullable=False, index=True
    )
    assigned_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
