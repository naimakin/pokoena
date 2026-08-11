import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TenantRole(str, enum.Enum):
    company_admin = "company_admin"
    company_employee = "company_employee"
    subcontractor = "subcontractor"


class UserTenantRole(Base):
    """One row per (user, tenant) membership. A user could in principle belong
    to multiple tenants, each with its own role — this table is what makes that
    possible even though the current onboarding flows only ever create one."""

    __tablename__ = "user_tenant_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id", name="uq_user_tenant_roles_user_tenant"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    role: Mapped[TenantRole] = mapped_column(SAEnum(TenantRole, name="tenant_role"), nullable=False)
    # Only set for role=subcontractor when the person belongs to a subcontractor firm.
    subcontractor_org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subcontractor_organizations.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
