import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.user_tenant_role import ProjectRole, TenantRole


class InviteCreate(BaseModel):
    email: EmailStr
    full_name: str
    title: str | None = None
    phone: str | None = None
    role: TenantRole
    # Required (checked in the route, not here) for role=company_employee/subcontractor;
    # company_admin invites aren't accepted through this endpoint at all.
    project_role: ProjectRole | None = None
    # Which projects this person gets a ProjectMembership row for. Meaningful for
    # role=company_employee; for role=subcontractor, project access instead comes
    # from project_scope_ids below (each scope already belongs to one project).
    project_ids: list[uuid.UUID] = []
    # Only meaningful for role=subcontractor:
    project_scope_ids: list[uuid.UUID] = []
    subcontractor_org_id: uuid.UUID | None = None


class InviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: TenantRole
    project_role: ProjectRole | None = None
    status: str
    expires_at: datetime
    # Only ever populated on the response to POST /invites, right after
    # creation — see services/invites.create_invite. GET /invites (the list)
    # can't reconstruct it: only the token's hash is persisted.
    invite_url: str | None = None


class InvitePreview(BaseModel):
    email: str
    full_name: str
    title: str | None = None
    role: TenantRole
    project_role: ProjectRole | None = None
    tenant_name: str
    expires_at: datetime


class InviteAccept(BaseModel):
    password: str
