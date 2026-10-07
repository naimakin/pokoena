import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Generic JSON everywhere (needed for the SQLite test suite); real JSONB on Postgres.
_JSON = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


class TenantRole(str, enum.Enum):
    company_admin = "company_admin"
    company_employee = "company_employee"
    subcontractor = "subcontractor"


class ProjectRole(str, enum.Enum):
    """What a company_employee/subcontractor is allowed to do, tenant-wide
    (not per-project — a person can hold several of these at once, across
    every project they're assigned to; stored as a JSON list of values
    rather than a Postgres ARRAY-of-enum so SQLite, the pytest suite's
    engine, can store it too). company_admin rows never set this: their
    TenantRole already implies unrestricted access, same reasoning as
    ProjectMembership skipping company admins entirely.

    The roles follow the product's menus (Overview / Programme / Delivery /
    Risk / Reports); what each one unlocks is ROLE_CAPABILITIES below, and the
    routes check capabilities, never role names (deps.require_capability)."""

    project_manager = "project_manager"
    planner = "planner"
    delivery_team = "delivery_team"
    viewer = "viewer"
    dashboard_viewer = "dashboard_viewer"
    user_management = "user_management"
    # Subcontractors only: update progress on their own scope.
    activity_status_updater = "activity_status_updater"


PROJECT_ROLE_LABELS: dict[ProjectRole, str] = {
    ProjectRole.project_manager: "Project Manager",
    ProjectRole.planner: "Planner",
    ProjectRole.delivery_team: "Delivery Team",
    ProjectRole.viewer: "Viewer",
    ProjectRole.dashboard_viewer: "Dashboard Viewer",
    ProjectRole.user_management: "User Management",
    ProjectRole.activity_status_updater: "Update progress",
}


class Capability(str, enum.Enum):
    view_overview = "view_overview"
    view_programme = "view_programme"
    edit_programme = "edit_programme"  # WBS, calendars, resources, codes, Scenario Lab, DCMA targets
    import_programme = "import_programme"  # .xer upload, current import, edit/delete imports
    manage_baselines = "manage_baselines"
    export = "export"  # XER, Excel, CSV downloads, Export / Sync to P6
    view_delivery = "view_delivery"
    edit_progress = "edit_progress"  # activity progress, EVM progress, recovery-plan authoring
    view_risk = "view_risk"
    edit_risk = "edit_risk"
    view_reports = "view_reports"
    edit_reports = "edit_reports"  # report designs
    manage_users = "manage_users"
    # Company admin only — no role grants these.
    manage_projects = "manage_projects"


C = Capability
_SEE_ALL = {C.view_overview, C.view_programme, C.view_delivery, C.view_risk, C.view_reports}

ROLE_CAPABILITIES: dict[ProjectRole, frozenset[Capability]] = {
    ProjectRole.project_manager: frozenset(
        _SEE_ALL
        | {C.edit_programme, C.import_programme, C.manage_baselines, C.export, C.edit_progress, C.edit_risk, C.edit_reports}
    ),
    ProjectRole.planner: frozenset(
        _SEE_ALL | {C.edit_programme, C.import_programme, C.manage_baselines, C.export, C.edit_risk, C.edit_reports}
    ),
    ProjectRole.delivery_team: frozenset(_SEE_ALL | {C.edit_progress, C.export, C.edit_reports}),
    ProjectRole.viewer: frozenset(_SEE_ALL),
    ProjectRole.dashboard_viewer: frozenset({C.view_overview, C.view_reports}),
    ProjectRole.user_management: frozenset({C.manage_users}),
    # A subcontractor's access is their scope (deps.require_scope_access), not capabilities.
    ProjectRole.activity_status_updater: frozenset(),
}

ALL_CAPABILITIES = frozenset(Capability)
VIEW_ANY = tuple(sorted(_SEE_ALL, key=lambda c: c.value))

COMPANY_PROJECT_ROLES = {r for r in ProjectRole if r != ProjectRole.activity_status_updater}

# Roles only a company admin may hand out (services/team_roles.py): they
# import, set baselines or manage people — a User Management employee could
# otherwise mint peers with more reach than they should.
ADMIN_GRANTED_PROJECT_ROLES = {ProjectRole.project_manager, ProjectRole.planner, ProjectRole.user_management}

# The only project role a subcontractor may hold: update progress on the
# activities of their own scopes. Without it they're view only. What they see
# is decided by their scopes (WBS / activity code rules, services/
# scope_rules.py), never by a company role.
SUBCONTRACTOR_PROJECT_ROLES = {ProjectRole.activity_status_updater}

# Roles before the menu-based model (migration 0034). Rows are rewritten by
# that migration, but code reading a row in the deploy window before it runs
# (or an old invite) still has to understand them.
LEGACY_ROLE_MAP: dict[str, list[str]] = {
    "project_administrator": ["project_manager"],
    "all_access": ["project_manager"],
    "execution": ["delivery_team"],
}


def parse_project_roles(raw: list[str] | None, tenant_role: "TenantRole | None" = None) -> list[ProjectRole]:
    """Stored role strings -> ProjectRole, mapping legacy values and dropping
    unknown ones (never a 500 on a stale row). A legacy employee holding
    activity_status_updater is a Delivery Team member now."""
    out: list[ProjectRole] = []
    for value in raw or []:
        mapped = LEGACY_ROLE_MAP.get(value, [value])
        if value == "activity_status_updater" and tenant_role == TenantRole.company_employee:
            mapped = ["delivery_team"]
        for v in mapped:
            try:
                role = ProjectRole(v)
            except ValueError:
                continue
            if role not in out:
                out.append(role)
    return out


def capabilities_for(tenant_role: "TenantRole", project_roles: list[ProjectRole]) -> frozenset[Capability]:
    if tenant_role == TenantRole.company_admin:
        return ALL_CAPABILITIES
    if tenant_role == TenantRole.subcontractor:
        return frozenset()
    caps: set[Capability] = set()
    for role in project_roles:
        caps |= ROLE_CAPABILITIES.get(role, frozenset())
    return frozenset(caps)


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
    # list[str] of ProjectRole values, not list[ProjectRole] — JSON round-trips
    # plain strings; callers convert via [ProjectRole(r) for r in ...] (see
    # deps.get_current_tenant_user). Required (enforced in the invites route,
    # not the DB) to be non-empty for company_employee/subcontractor; left
    # empty for company_admin.
    project_roles: Mapped[list[str]] = mapped_column(_JSON, nullable=False, default=list)
    # Only set for role=subcontractor when the person belongs to a subcontractor firm.
    subcontractor_org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subcontractor_organizations.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
