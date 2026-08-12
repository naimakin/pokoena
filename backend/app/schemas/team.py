import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.user_tenant_role import ProjectRole, TenantRole


class TeamMemberOut(BaseModel):
    user_tenant_role_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    title: str | None = None
    phone: str | None = None
    role: TenantRole
    project_role: ProjectRole | None = None
    is_active: bool
    created_at: datetime
