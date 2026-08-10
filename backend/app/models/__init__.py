"""Importing this package registers every model on Base.metadata — required
by Alembic autogenerate and by tests that call Base.metadata.create_all()."""

from app.models.activity import Activity, ActivityStatus
from app.models.activity_relationship import ActivityRelationship, LinkType
from app.models.change_request import ChangeRequest, ChangeRequestStatus, RiskLevel
from app.models.company import Company
from app.models.project import Project
from app.models.scope_submission import ScopeSubmission
from app.models.update_period import UpdatePeriod, UpdatePeriodStatus
from app.models.user import User, UserRole

__all__ = [
    "Activity",
    "ActivityStatus",
    "ActivityRelationship",
    "LinkType",
    "ChangeRequest",
    "ChangeRequestStatus",
    "RiskLevel",
    "Company",
    "Project",
    "ScopeSubmission",
    "UpdatePeriod",
    "UpdatePeriodStatus",
    "User",
    "UserRole",
]
