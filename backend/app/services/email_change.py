"""Changing a team member's sign-in email (PATCH /team/{id}, company admin only).

A `users` row is global — one account can belong to several tenants — so an
admin of one company must never be able to re-point an account another
company also uses. And because accepting an invite resets the password of
whatever account has the invite's email (services/invites.accept_invite),
an email that has a pending invite anywhere is refused too: otherwise that
invite's holder would take over the renamed account. Both checks read across
tenants, which is exactly what RLS hides from the request session, so they use
the narrow bypass session — same reasoning as auth._active_tenant_id_for_user.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.db.session import BypassSessionLocal
from app.models.invite import Invite, InviteStatus
from app.models.user import User
from app.models.user_tenant_role import UserTenantRole


def check_email_change(user: User, tenant_id: uuid.UUID, new_email: str) -> str:
    """Returns the normalised new email, or raises 400/409."""
    email = new_email.strip().lower()
    if user.is_platform_admin:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This account's email can't be changed here")
    bypass_db = BypassSessionLocal()
    try:
        if _in_other_tenant(bypass_db, user.id, tenant_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This person also belongs to another company; their email can't be changed here",
            )
        taken = bypass_db.query(User.id).filter(User.email == email, User.id != user.id).first()
        if taken is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Another account already uses that email")
        now = datetime.now(timezone.utc)
        pending = (
            bypass_db.query(Invite)
            .filter(Invite.email == email, Invite.status == InviteStatus.pending)
            .all()
        )
        if any(_aware(i.expires_at) > now for i in pending):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="There's a pending invite for that email — revoke it first"
            )
    finally:
        bypass_db.close()
    return email


def _in_other_tenant(bypass_db, user_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
    return (
        bypass_db.query(UserTenantRole.id)
        .filter(UserTenantRole.user_id == user_id, UserTenantRole.tenant_id != tenant_id)
        .first()
        is not None
    )


def belongs_to_another_tenant(user_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
    """For credential actions (reset links) one company must not take on an
    account another company also uses."""
    bypass_db = BypassSessionLocal()
    try:
        return _in_other_tenant(bypass_db, user_id, tenant_id)
    finally:
        bypass_db.close()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
