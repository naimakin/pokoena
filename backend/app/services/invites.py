import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import BypassSessionLocal, set_rls_context
from app.models.invite import Invite, InviteStatus
from app.models.project_membership import ProjectMembership
from app.models.subcontractor_scope_assignment import SubcontractorScopeAssignment
from app.models.user import User
from app.models.user_tenant_role import ProjectRole, TenantRole, UserTenantRole
from app.worker.tasks import send_invite_email

INVITE_EXPIRY = timedelta(hours=72)


class InviteError(Exception):
    """Invalid, expired, or already-used invite token."""


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _as_aware_utc(dt: datetime) -> datetime:
    """SQLite (the pytest suite's engine) ignores DateTime(timezone=True) and
    always hands back naive datetimes, even though every value is written as
    UTC-aware; Postgres round-trips tz-aware values correctly, so this is a
    no-op there. Values are always written as UTC, so a naive value is assumed
    to be UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def create_invite(
    db: Session,
    tenant_id: uuid.UUID,
    email: str,
    role: TenantRole,
    invited_by_user_id: uuid.UUID,
    full_name: str = "",
    title: str | None = None,
    phone: str | None = None,
    project_roles: list[ProjectRole] | None = None,
    tenant_name: str | None = None,
    payload: dict | None = None,
) -> tuple[Invite, str]:
    """`payload` carries what acceptance should materialize beyond the base
    UserTenantRole row: `{"project_scope_ids": [...]}` for subcontractors,
    `{"project_ids": [...]}` for company employees, `{"subcontractor_org_id": ...}`
    to attach a subcontractor to a firm. Only the token's hash is ever stored —
    the raw value is handed straight to the Celery task that emails it and is
    never persisted. `full_name`/`title`/`phone`/`project_roles` are entered by
    the inviting admin, not the invitee — acceptance only ever collects a
    password.

    Returns `(invite, invite_url)` — the caller (an API route) is expected to
    hand `invite_url` straight back in its response so whoever created the
    invite can copy/paste it themselves. This is deliberately not email-only:
    no transactional email provider is wired up yet (see
    app/core/notifications.py), and the Celery task that *would* send it needs
    a `worker` process this deployment doesn't run — so a delivered email is
    not something an invite creator can rely on today. The URL is only ever
    obtainable here, at creation time, since only the token's hash is
    persisted afterward.

    Rejects emails that already belong to an existing User: `accept_invite`
    resets whatever user matches the invite's email to a password the
    accepter chooses, with no proof they ever controlled that account (no
    real email delivery exists to verify inbox ownership — see above). Since
    `invite_url` is handed straight back to whoever creates the invite, an
    unrestricted invite would let any company_admin/user_management member
    take over *any* existing account — including a platform admin's — just by
    knowing its email and inviting it into their own tenant. `users.email` is
    global (not tenant-scoped), so this check is a simple existence lookup."""
    if db.query(User).filter(User.email == email.lower()).first() is not None:
        raise InviteError(
            "An account with this email already exists — invites can only onboard new people right now."
        )

    raw_token = secrets.token_urlsafe(32)

    # Explicit even when the caller's session already has this tenant's RLS
    # context set (the common case) — also correct for the one-off case of a
    # platform admin creating the very first invite for a brand-new tenant,
    # whose session otherwise carries no tenant context at all.
    set_rls_context(db, tenant_id)

    invite = Invite(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email=email.lower(),
        full_name=full_name,
        title=title,
        phone=phone,
        role=role,
        project_roles=[r.value for r in (project_roles or [])],
        token_hash=_hash_token(raw_token),
        invited_by_user_id=invited_by_user_id,
        status=InviteStatus.pending,
        payload=payload or {},
        expires_at=datetime.now(timezone.utc) + INVITE_EXPIRY,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    send_invite_email.delay(
        to_email=invite.email, raw_token=raw_token, role=role.value, tenant_name=tenant_name
    )
    invite_url = f"{get_settings().frontend_url}/invite/{raw_token}"
    return invite, invite_url


def _invite_tenant_id_for_token(raw_token: str) -> uuid.UUID | None:
    """Bootstrap lookup: which tenant a token belongs to is exactly what's
    still unknown at this point, but RLS on `invites` requires
    app.current_tenant_id to already be set to the right value — a
    chicken-and-egg an ordinary RLS-bound session can't resolve on its own.
    The unguessable token itself is the authorization for this one read, same
    reasoning as the platform support-access path, so it goes through the
    BYPASSRLS connection rather than the caller's session."""
    bypass_db = BypassSessionLocal()
    try:
        row = (
            bypass_db.query(Invite.tenant_id)
            .filter(Invite.token_hash == _hash_token(raw_token))
            .first()
        )
        return row[0] if row else None
    finally:
        bypass_db.close()


def get_invite_preview(db: Session, raw_token: str) -> Invite:
    """Used by the public `GET /invites/{token}` preview."""
    tenant_id = _invite_tenant_id_for_token(raw_token)
    if tenant_id is None:
        raise InviteError("Invalid invite link")
    set_rls_context(db, tenant_id)

    invite = db.query(Invite).filter(Invite.token_hash == _hash_token(raw_token)).first()
    if invite is None:
        raise InviteError("Invalid invite link")
    if invite.status != InviteStatus.pending:
        raise InviteError("This invite has already been used or revoked")
    if _as_aware_utc(invite.expires_at) < datetime.now(timezone.utc):
        raise InviteError("This invite has expired")
    return invite


def accept_invite(db: Session, raw_token: str, password: str) -> tuple[User, Invite]:
    token_hash = _hash_token(raw_token)
    tenant_id = _invite_tenant_id_for_token(raw_token)
    if tenant_id is None:
        raise InviteError("Invalid invite link")

    # The invite itself is the authorization for everything below — it's a
    # valid, unexpired, single-use token scoped to exactly one tenant — so
    # it's safe to set RLS context to that tenant even though the person
    # accepting it isn't authenticated as a member of it yet. Setting it here
    # (rather than after the lookup below) is what makes that lookup, and its
    # row lock, possible at all under RLS.
    set_rls_context(db, tenant_id)

    query = db.query(Invite).filter(Invite.token_hash == token_hash)
    # SQLite (the pytest suite's engine) can't compile FOR UPDATE at all — real
    # row locking against a concurrent double-accept only matters, and is only
    # available, on the Postgres engine this runs against in every other case.
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        query = query.with_for_update()
    invite = query.first()
    if invite is None:
        raise InviteError("Invalid invite link")
    if invite.status != InviteStatus.pending:
        raise InviteError("This invite has already been used or revoked")
    if _as_aware_utc(invite.expires_at) < datetime.now(timezone.utc):
        invite.status = InviteStatus.expired
        db.commit()
        raise InviteError("This invite has expired")

    user = db.query(User).filter(User.email == invite.email).first()
    if user is None:
        user = User(
            id=uuid.uuid4(),
            email=invite.email,
            hashed_password=hash_password(password),
            full_name=invite.full_name,
            title=invite.title,
            phone=invite.phone,
            is_active=True,
        )
        db.add(user)
        db.flush()
    else:
        user.hashed_password = hash_password(password)
        user.full_name = invite.full_name
        user.title = invite.title
        user.phone = invite.phone
        user.is_active = True

    subcontractor_org_id = invite.payload.get("subcontractor_org_id")
    membership = (
        db.query(UserTenantRole)
        .filter(UserTenantRole.user_id == user.id, UserTenantRole.tenant_id == invite.tenant_id)
        .first()
    )
    if membership is None:
        membership = UserTenantRole(
            id=uuid.uuid4(),
            user_id=user.id,
            tenant_id=invite.tenant_id,
            role=invite.role,
            project_roles=invite.project_roles,
            subcontractor_org_id=uuid.UUID(subcontractor_org_id) if subcontractor_org_id else None,
            is_active=True,
        )
        db.add(membership)
    else:
        membership.role = invite.role
        membership.project_roles = invite.project_roles
        membership.is_active = True
        if subcontractor_org_id:
            membership.subcontractor_org_id = uuid.UUID(subcontractor_org_id)
    db.flush()

    if invite.role == TenantRole.subcontractor:
        for scope_id in invite.payload.get("project_scope_ids", []):
            scope_uuid = uuid.UUID(scope_id)
            already_assigned = (
                db.query(SubcontractorScopeAssignment)
                .filter(
                    SubcontractorScopeAssignment.user_id == user.id,
                    SubcontractorScopeAssignment.project_scope_id == scope_uuid,
                )
                .first()
            )
            if already_assigned is None:
                db.add(
                    SubcontractorScopeAssignment(
                        id=uuid.uuid4(),
                        tenant_id=invite.tenant_id,
                        user_id=user.id,
                        project_scope_id=scope_uuid,
                        assigned_by_user_id=invite.invited_by_user_id,
                    )
                )
    elif invite.role == TenantRole.company_employee:
        for project_id_str in invite.payload.get("project_ids", []):
            project_id = uuid.UUID(project_id_str)
            existing = (
                db.query(ProjectMembership)
                .filter(ProjectMembership.user_id == user.id, ProjectMembership.project_id == project_id)
                .first()
            )
            if existing is None:
                db.add(
                    ProjectMembership(
                        id=uuid.uuid4(),
                        tenant_id=invite.tenant_id,
                        project_id=project_id,
                        user_id=user.id,
                    )
                )

    invite.status = InviteStatus.accepted
    invite.accepted_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(user)
    db.refresh(invite)
    return user, invite
