"""Importing this package registers every model on Base.metadata — required
by Alembic autogenerate and by tests that call Base.metadata.create_all()."""

from app.models.activity import Activity, ActivityStatus
from app.models.activity_relationship import ActivityRelationship, LinkType
from app.models.audit_log import AuditLog
from app.models.change_request import ChangeRequest, ChangeRequestStatus, RiskLevel
from app.models.invite import Invite, InviteStatus
from app.models.password_reset import PasswordReset
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.project_scope import ProjectScope
from app.models.scope_submission import ScopeSubmission
from app.models.subcontractor_organization import SubcontractorOrganization
from app.models.subcontractor_scope_assignment import SubcontractorScopeAssignment
from app.models.tenant import Tenant, TenantStatus
from app.models.update_period import UpdatePeriod, UpdatePeriodStatus
from app.models.user import User
from app.models.user_identity import IdentityProvider, UserIdentity
from app.models.user_tenant_role import (
    EDIT_CAPABLE_PROJECT_ROLES,
    PROJECT_ROLE_LABELS,
    USER_MANAGEMENT_CAPABLE_PROJECT_ROLES,
    ProjectRole,
    TenantRole,
    UserTenantRole,
)

__all__ = [
    "Activity",
    "ActivityStatus",
    "ActivityRelationship",
    "LinkType",
    "AuditLog",
    "ChangeRequest",
    "ChangeRequestStatus",
    "RiskLevel",
    "Invite",
    "InviteStatus",
    "PasswordReset",
    "Project",
    "ProjectMembership",
    "ProjectScope",
    "ScopeSubmission",
    "SubcontractorOrganization",
    "SubcontractorScopeAssignment",
    "Tenant",
    "TenantStatus",
    "UpdatePeriod",
    "UpdatePeriodStatus",
    "User",
    "IdentityProvider",
    "UserIdentity",
    "TenantRole",
    "UserTenantRole",
    "ProjectRole",
    "PROJECT_ROLE_LABELS",
    "EDIT_CAPABLE_PROJECT_ROLES",
    "USER_MANAGEMENT_CAPABLE_PROJECT_ROLES",
]
