import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.user_tenant_role import ProjectRole, TenantRole


class TeamMemberOut(BaseModel):
    user_tenant_role_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    title: str | None = None
    phone: str | None = None
    role: TenantRole
    project_roles: list[ProjectRole] = []
    is_active: bool
    created_at: datetime
    # Company employees: the projects they're a member of.
    project_ids: list[uuid.UUID] = []
    # Subcontractors: their scopes (each belongs to one project) and firm.
    scope_ids: list[uuid.UUID] = []
    subcontractor_org_id: uuid.UUID | None = None
    subcontractor_org_name: str | None = None


class TeamMemberUpdate(BaseModel):
    """PATCH /team/{id}: every field optional; only what's sent changes."""

    # Company admin only; refused for accounts other companies also use
    # (services/email_change.py).
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    title: str | None = None
    phone: str | None = None
    project_roles: list[ProjectRole] | None = None
    project_ids: list[uuid.UUID] | None = None
    scope_ids: list[uuid.UUID] | None = None
    subcontractor_org_id: uuid.UUID | None = None
    # True restores a removed member; removing still goes through DELETE.
    is_active: bool | None = None
