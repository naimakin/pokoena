import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.user_tenant_role import TenantRole


class TeamMemberOut(BaseModel):
    user_tenant_role_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    role: TenantRole
    is_active: bool
    created_at: datetime
