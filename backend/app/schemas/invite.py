import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.project_membership import ProjectPermission
from app.models.user_tenant_role import TenantRole


class ProjectMembershipInput(BaseModel):
    project_id: uuid.UUID
    permission: ProjectPermission = ProjectPermission.view


class InviteCreate(BaseModel):
    email: EmailStr
    role: TenantRole
    full_name: str | None = None
    # Only meaningful for role=company_employee:
    project_memberships: list[ProjectMembershipInput] = []
    # Only meaningful for role=subcontractor:
    project_scope_ids: list[uuid.UUID] = []
    subcontractor_org_id: uuid.UUID | None = None


class InviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: TenantRole
    status: str
    expires_at: datetime


class InvitePreview(BaseModel):
    email: str
    role: TenantRole
    tenant_name: str
    expires_at: datetime


class InviteAccept(BaseModel):
    full_name: str
    password: str
