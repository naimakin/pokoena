import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import set_rls_context
from app.models.invite import Invite, InviteStatus
from app.models.project_membership import ProjectMembership, ProjectPermission
from app.models.subcontractor_scope_assignment import SubcontractorScopeAssignment
from app.models.user import User
from app.models.user_tenant_role import TenantRole, UserTenantRole
from app.worker.tasks import send_invite_email

INVITE_EXPIRY = timedelta(hours=72)


class InviteError(Exception):
    """Invalid, expired, or already-used invite token."""


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_invite(
    db: Session,
    tenant_id: uuid.UUID,
    email: str,
    role: TenantRole,
    invited_by_user_id: uuid.UUID,
    tenant_name: str | None = None,
    payload: dict | None = None,
) -> Invite:
    """`payload` carries what acceptance should materialize beyond the base
    UserTenantRole row: `{"project_scope_ids": [...]}` for subcontractors,
    `{"project_memberships": [{"project_id": ..., "permission": ...}]}` for
    company employees, `{"subcontractor_org_id": ...}` to attach a subcontractor
    to a firm. Only the token's hash is ever stored — the raw value is handed
    straight to the Celery task that emails it and is never persisted."""
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
        role=role,
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
    return invite


def get_invite_preview(db: Session, raw_token: str) -> Invite:
    """Used by the public `GET /invites/{token}` preview — no session/tenant
    context needed since it's a read the invite token itself already justifies."""
    invite = db.query(Invite).filter(Invite.token_hash == _hash_token(raw_token)).first()
    if invite is None:
        raise InviteError("Invalid invite link")
    if invite.status != InviteStatus.pending:
        raise InviteError("This invite has already been used or revoked")
    if invite.expires_at < datetime.now(timezone.utc):
        raise InviteError("This invite has expired")
    return invite


def accept_invite(db: Session, raw_token: str, password: str, full_name: str) -> tuple[User, Invite]:
    token_hash = _hash_token(raw_token)
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
    if invite.expires_at < datetime.now(timezone.utc):
        invite.status = InviteStatus.expired
        db.commit()
        raise InviteError("This invite has expired")

    # The invite itself is the authorization for everything below — it's a
    # valid, unexpired, single-use token scoped to exactly one tenant — so it's
    # safe to set RLS context to that tenant even though the person accepting
    # it isn't authenticated as a member of it yet.
    set_rls_context(db, invite.tenant_id)

    user = db.query(User).filter(User.email == invite.email).first()
    if user is None:
        user = User(
            id=uuid.uuid4(),
            email=invite.email,
            hashed_password=hash_password(password),
            full_name=full_name,
            is_active=True,
        )
        db.add(user)
        db.flush()
    else:
        user.hashed_password = hash_password(password)
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
            subcontractor_org_id=uuid.UUID(subcontractor_org_id) if subcontractor_org_id else None,
            is_active=True,
        )
        db.add(membership)
    else:
        membership.role = invite.role
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
        for entry in invite.payload.get("project_memberships", []):
            project_id = uuid.UUID(entry["project_id"])
            permission = ProjectPermission(entry.get("permission", "view"))
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
                        permission=permission,
                    )
                )
            else:
                existing.permission = permission

    invite.status = InviteStatus.accepted
    invite.accepted_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(user)
    db.refresh(invite)
    return user, invite
