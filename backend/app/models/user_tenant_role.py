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


class ProjectRole(str, enum.Enum):
    """What a company_employee/subcontractor is allowed to do, tenant-wide
    (not per-project — a person holds exactly one of these across every
    project they're assigned to). company_admin rows never set this: their
    TenantRole already implies unrestricted access, same reasoning as
    ProjectMembership skipping company admins entirely."""

    project_administrator = "project_administrator"
    all_access = "all_access"
    execution = "execution"
    user_management = "user_management"
    activity_status_updater = "activity_status_updater"


PROJECT_ROLE_LABELS: dict[ProjectRole, str] = {
    ProjectRole.project_administrator: "Project Administrator",
    ProjectRole.all_access: "All Access (No Threshold Settings)",
    ProjectRole.execution: "Execution",
    ProjectRole.user_management: "User Management",
    ProjectRole.activity_status_updater: "Activity Status Updater",
}

# Roles that may edit schedule/execution data (activities, progress). Kept as
# a set rather than per-role branching so deps.require_project_permission and
# any future field-level check share one definition instead of drifting.
EDIT_CAPABLE_PROJECT_ROLES = {
    ProjectRole.project_administrator,
    ProjectRole.all_access,
    ProjectRole.execution,
    ProjectRole.activity_status_updater,
}

# Roles that may manage team members (in addition to company_admin, which
# always can regardless of project_role).
USER_MANAGEMENT_CAPABLE_PROJECT_ROLES = {
    ProjectRole.project_administrator,
    ProjectRole.user_management,
}


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
    # Required (enforced in the invites route, not the DB) for company_employee
    # and subcontractor; left null for company_admin.
    project_role: Mapped[ProjectRole | None] = mapped_column(
        SAEnum(ProjectRole, name="project_role"), nullable=True
    )
    # Only set for role=subcontractor when the person belongs to a subcontractor firm.
    subcontractor_org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subcontractor_organizations.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
