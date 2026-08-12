import uuid

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.user_tenant_role import ProjectRole, TenantRole


class UserOut(BaseModel):
    """The tenant-side "who am I" shape: identity plus the caller's membership
    in the tenant their token is scoped to. There is no bare global `role` on
    User anymore — role only ever exists in the context of one tenant."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    title: str | None = None
    phone: str | None = None
    is_active: bool
    tenant_id: uuid.UUID
    role: TenantRole
    project_role: ProjectRole | None = None
    scope_ids: list[uuid.UUID] = []


class PlatformAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    title: str | None = None
    phone: str | None = None
    is_active: bool


class PlatformAdminCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    title: str | None = None
    phone: str | None = None
