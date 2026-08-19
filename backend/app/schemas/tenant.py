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
    # Not on the Tenant row itself — populated by list_tenants/create_tenant
    # from a UserTenantRole lookup. None if the admin invite was never
    # accepted yet (no User row exists for that email until then), or in the
    # rare case a tenant somehow has no company_admin.
    admin_email: str | None = None
    # False while admin_email only reflects a still-pending invite (no User
    # row exists yet) — tells the frontend to offer "Resend invite" instead
    # of "Reset password" in that case.
    admin_accepted: bool = False


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


class TenantInviteLinkOut(BaseModel):
    """Returned by resend-admin-invite — a fresh one-time link, same
    recoverability rule as TenantCreateOut.admin_invite_url: only ever
    obtainable right when the invite is (re)created."""

    email: str
    invite_url: str


class UsageSummary(BaseModel):
    """Aggregate, anonymized counts only — never row-level tenant business data.
    See app/api/routes/platform.py for how these are computed (per-tenant RLS
    context, summed — not the BYPASSRLS support-access path)."""

    tenant_count: int
    active_tenant_count: int
    total_users: int
    total_projects: int
