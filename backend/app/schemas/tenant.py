import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.tenant import TenantStatus


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    status: TenantStatus
    created_at: datetime


class TenantCreate(BaseModel):
    name: str
    slug: str
    admin_email: EmailStr
    admin_full_name: str


class TenantCreateOut(TenantOut):
    """Same shape as TenantOut plus the one-time invite link for the first
    company admin — see services/invites.create_invite for why this is the
    only place that link is ever recoverable."""

    admin_invite_url: str


class UsageSummary(BaseModel):
    """Aggregate, anonymized counts only — never row-level tenant business data.
    See app/api/routes/platform.py for how these are computed (per-tenant RLS
    context, summed — not the BYPASSRLS support-access path)."""

    tenant_count: int
    active_tenant_count: int
    total_users: int
    total_projects: int
