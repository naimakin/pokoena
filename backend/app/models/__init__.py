"""Importing this package registers every model on Base.metadata — required
by Alembic autogenerate and by tests that call Base.metadata.create_all()."""

from app.models.activity import Activity, ActivityStatus
from app.models.activity_code import ActivityCodeType, ActivityCodeValue, TaskActivityCode
from app.models.activity_event import ActivityEvent
from app.models.activity_relationship import ActivityRelationship, LinkType
from app.models.audit_log import AuditLog
from app.models.baseline import (
    Baseline,
    BaselineActivity,
    BaselinePvCurve,
    BaselineResource,
    BaselineResourceAssignment,
    BaselineStatus,
)
from app.models.calendar import Calendar
from app.models.change_request import ChangeRequest, ChangeRequestStatus, RiskLevel
from app.models.dashboard_layout import DashboardLayout
from app.models.evm_snapshot import EvmSnapshot
from app.models.invite import Invite, InviteStatus
from app.models.password_reset import PasswordReset
from app.models.progress_entry import ProgressEntry, ProgressEntryType
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.project_scope import ProjectScope
from app.models.report_format import ReportFormat
from app.models.recovery_plan import (
    RecoveryItemStatus,
    RecoveryPlan,
    RecoveryPlanItem,
    RecoveryPlanStatus,
)
from app.models.resource import Resource
from app.models.resource_assignment import ResourceAssignment
from app.models.risk_analysis import RiskAnalysisSettings, RiskSimulationRun
from app.models.risk_item import (
    MitigationStatus,
    MitigationStrategy,
    RiskActionItem,
    RiskActionStatus,
    RiskItem,
    RiskStatus,
)
from app.models.saved_activity_filter import SavedActivityFilter
from app.models.schedule_export import ScheduleExport
from app.models.schedule_import import ScheduleImport
from app.models.schedule_status_snapshot import ScheduleStatusSnapshot
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
from app.models.wbs_node import WbsNode

__all__ = [
    "Activity",
    "ActivityStatus",
    "ActivityCodeType",
    "ActivityCodeValue",
    "ActivityEvent",
    "TaskActivityCode",
    "ActivityRelationship",
    "LinkType",
    "AuditLog",
    "Baseline",
    "BaselineActivity",
    "BaselinePvCurve",
    "BaselineResource",
    "BaselineResourceAssignment",
    "BaselineStatus",
    "Calendar",
    "ScheduleExport",
    "ScheduleImport",
    "ScheduleStatusSnapshot",
    "ChangeRequest",
    "ChangeRequestStatus",
    "RiskLevel",
    "DashboardLayout",
    "EvmSnapshot",
    "Invite",
    "InviteStatus",
    "PasswordReset",
    "ProgressEntry",
    "ProgressEntryType",
    "Project",
    "ProjectMembership",
    "ProjectScope",
    "RecoveryPlan",
    "RecoveryPlanItem",
    "RecoveryPlanStatus",
    "ReportFormat",
    "RecoveryItemStatus",
    "Resource",
    "ResourceAssignment",
    "RiskAnalysisSettings",
    "RiskSimulationRun",
    "RiskItem",
    "RiskActionItem",
    "RiskStatus",
    "MitigationStatus",
    "MitigationStrategy",
    "RiskActionStatus",
    "SavedActivityFilter",
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
    "WbsNode",
]
