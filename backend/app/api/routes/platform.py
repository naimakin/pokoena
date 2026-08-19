import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import BypassSessionLocal, get_db, set_rls_context
from app.deps import get_current_platform_admin
from app.models.activity import Activity
from app.models.invite import Invite, InviteStatus
from app.models.project import Project
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.models.user_tenant_role import TenantRole, UserTenantRole
from app.schemas.password_reset import PasswordResetLinkOut
from app.schemas.tenant import TenantCreate, TenantCreateOut, TenantInviteLinkOut, TenantOut, UsageSummary
from app.schemas.user import PlatformAdminCreate, PlatformAdminOut
from app.services import audit
from app.services.invites import InviteError, create_invite
from app.services.password_reset import create_password_reset

router = APIRouter(prefix="/platform", tags=["platform"])


def _admin_info_by_tenant(tenant_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[str, bool]]:
    """Cross-tenant by nature (one row per tenant, read from the platform
    admin's own list page) — uses the BYPASSRLS connection like the other
    platform-wide aggregates in this file, never row-level tenant business
    data. Value is (email, accepted) — accepted membership wins over a
    still-pending invite, which is shown so a freshly-onboarded tenant
    displays something immediately. `accepted` tells the frontend whether to
    offer Reset password (an account exists) or Resend invite (it doesn't)."""
    if not tenant_ids:
        return {}
    bypass_db = BypassSessionLocal()
    try:
        info: dict[uuid.UUID, tuple[str, bool]] = {}
        for tenant_id, email in (
            bypass_db.query(Invite.tenant_id, Invite.email)
            .filter(Invite.tenant_id.in_(tenant_ids), Invite.role == TenantRole.company_admin, Invite.status == InviteStatus.pending)
            .all()
        ):
            info[tenant_id] = (email, False)
        for tenant_id, email in (
            bypass_db.query(UserTenantRole.tenant_id, User.email)
            .join(User, User.id == UserTenantRole.user_id)
            .filter(
                UserTenantRole.tenant_id.in_(tenant_ids),
                UserTenantRole.role == TenantRole.company_admin,
                UserTenantRole.is_active.is_(True),
            )
            .all()
        ):
            info[tenant_id] = (email, True)
        return info
    finally:
        bypass_db.close()


@router.post("/tenants", response_model=TenantCreateOut, status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreate,
    db: Session = Depends(get_db),
    platform_admin: User = Depends(get_current_platform_admin),
) -> TenantCreateOut:
    if db.query(Tenant).filter(Tenant.slug == payload.slug).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already in use")
    # Checked before the tenant row is created (not left to create_invite's own
    # check below) so a rejected admin email doesn't leave an orphaned tenant
    # with no admin invite behind.
    if db.query(User).filter(User.email == payload.admin_email.lower()).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists"
        )

    tenant = Tenant(id=uuid.uuid4(), name=payload.name, slug=payload.slug, status=TenantStatus.active)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    try:
        _invite, invite_url = create_invite(
            db=db,
            tenant_id=tenant.id,
            email=payload.admin_email,
            full_name=payload.admin_full_name,
            role=TenantRole.company_admin,
            invited_by_user_id=platform_admin.id,
            tenant_name=tenant.name,
        )
    except InviteError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    audit.log(
        "tenant.created", tenant_id=tenant.id, actor_user_id=platform_admin.id,
        target_type="tenant", target_id=tenant.id, event_metadata={"name": tenant.name},
    )
    return TenantCreateOut(
        id=tenant.id, name=tenant.name, slug=tenant.slug, status=tenant.status,
        created_at=tenant.created_at, admin_invite_url=invite_url, admin_email=payload.admin_email,
    )


@router.get("/tenants", response_model=list[TenantOut])
def list_tenants(
    db: Session = Depends(get_db), _: User = Depends(get_current_platform_admin)
) -> list[TenantOut]:
    tenants = db.query(Tenant).order_by(Tenant.created_at.desc()).all()
    admin_info = _admin_info_by_tenant([t.id for t in tenants])
    return [
        TenantOut(
            id=t.id, name=t.name, slug=t.slug, status=t.status, created_at=t.created_at,
            admin_email=admin_info.get(t.id, (None, False))[0],
            admin_accepted=admin_info.get(t.id, (None, False))[1],
        )
        for t in tenants
    ]


@router.post("/tenants/{tenant_id}/suspend", response_model=TenantOut)
def suspend_tenant(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
    platform_admin: User = Depends(get_current_platform_admin),
) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    tenant.status = TenantStatus.suspended
    db.commit()
    db.refresh(tenant)
    audit.log(
        "tenant.suspended", tenant_id=tenant.id, actor_user_id=platform_admin.id,
        target_type="tenant", target_id=tenant.id,
    )
    return tenant


@router.post("/tenants/{tenant_id}/admin-reset-link", response_model=PasswordResetLinkOut)
def create_tenant_admin_reset_link(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
    platform_admin: User = Depends(get_current_platform_admin),
) -> PasswordResetLinkOut:
    """Lets a platform admin hand a tenant's company_admin a way back into
    their account without needing a real email provider — same "surface the
    link directly" reasoning as onboarding invites. Only works once that
    admin has actually accepted their invite (there's no password to reset
    before then; re-sending the invite link is the right move at that
    stage, not this)."""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    bypass_db = BypassSessionLocal()
    try:
        row = (
            bypass_db.query(UserTenantRole.user_id, User.email)
            .join(User, User.id == UserTenantRole.user_id)
            .filter(
                UserTenantRole.tenant_id == tenant_id,
                UserTenantRole.role == TenantRole.company_admin,
                UserTenantRole.is_active.is_(True),
            )
            .first()
        )
    finally:
        bypass_db.close()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This tenant's admin hasn't accepted their invite yet — there's no account to reset",
        )
    admin_user_id, admin_email = row

    _reset, reset_url = create_password_reset(db, user_id=admin_user_id, created_by_user_id=platform_admin.id)
    audit.log(
        "password_reset.created", tenant_id=tenant_id, actor_user_id=platform_admin.id,
        target_type="user", target_id=admin_user_id,
    )
    return PasswordResetLinkOut(email=admin_email, reset_url=reset_url)


@router.post("/tenants/{tenant_id}/resend-admin-invite", response_model=TenantInviteLinkOut)
def resend_tenant_admin_invite(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
    platform_admin: User = Depends(get_current_platform_admin),
) -> TenantInviteLinkOut:
    """The counterpart to admin-reset-link for the other half of the invite's
    lifecycle: before it's ever accepted. create_invite's URL is only ever
    obtainable once, at creation time (see services/invites.create_invite) —
    if the platform admin lost that first link (closed the tab, etc.) there
    was previously no way to recover it short of querying the database
    directly. Revokes whatever invite the admin previously had (pending or
    expired — a stale token left active isn't useful and shouldn't linger)
    and issues a fresh one to the same email."""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    bypass_db = BypassSessionLocal()
    try:
        already_accepted = (
            bypass_db.query(UserTenantRole.id)
            .filter(
                UserTenantRole.tenant_id == tenant_id,
                UserTenantRole.role == TenantRole.company_admin,
                UserTenantRole.is_active.is_(True),
            )
            .first()
            is not None
        )
    finally:
        bypass_db.close()
    if already_accepted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This tenant's admin already has an account — use Reset password instead.",
        )

    set_rls_context(db, tenant_id)
    old_invite = (
        db.query(Invite)
        .filter(Invite.tenant_id == tenant_id, Invite.role == TenantRole.company_admin)
        .order_by(Invite.created_at.desc())
        .first()
    )
    if old_invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No admin invite found for this tenant")

    if old_invite.status == InviteStatus.pending:
        old_invite.status = InviteStatus.revoked
        db.commit()

    try:
        _invite, invite_url = create_invite(
            db=db,
            tenant_id=tenant_id,
            email=old_invite.email,
            full_name=old_invite.full_name,
            role=TenantRole.company_admin,
            invited_by_user_id=platform_admin.id,
            tenant_name=tenant.name,
        )
    except InviteError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    audit.log(
        "tenant.admin_invite_resent", tenant_id=tenant_id, actor_user_id=platform_admin.id,
        target_type="tenant", target_id=tenant_id,
    )
    return TenantInviteLinkOut(email=old_invite.email, invite_url=invite_url)


@router.post("/tenants/{tenant_id}/activate", response_model=TenantOut)
def activate_tenant(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
    platform_admin: User = Depends(get_current_platform_admin),
) -> Tenant:
    """Reverses suspend or (soft) delete — the tenant's business data was
    never touched by either, so flipping status back to active is all this
    needs to do."""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    if tenant.status == TenantStatus.active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant is already active")
    tenant.status = TenantStatus.active
    db.commit()
    db.refresh(tenant)
    audit.log(
        "tenant.activated", tenant_id=tenant.id, actor_user_id=platform_admin.id,
        target_type="tenant", target_id=tenant.id,
    )
    return tenant


@router.delete("/tenants/{tenant_id}", response_model=TenantOut)
def delete_tenant(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
    platform_admin: User = Depends(get_current_platform_admin),
) -> Tenant:
    """Soft delete — flips status only. RLS-scoped business data for this
    tenant is left in place (and stays inaccessible to it, since its status no
    longer allows login); a hard-delete/export flow is a separate, deliberate
    operation this endpoint doesn't perform."""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    tenant.status = TenantStatus.deleted
    db.commit()
    db.refresh(tenant)
    audit.log(
        "tenant.deleted", tenant_id=tenant.id, actor_user_id=platform_admin.id,
        target_type="tenant", target_id=tenant.id,
    )
    return tenant


@router.get("/usage", response_model=UsageSummary)
def usage_summary(
    db: Session = Depends(get_db), _: User = Depends(get_current_platform_admin)
) -> UsageSummary:
    """Aggregate counts only — computed by setting RLS context to each tenant in
    turn and counting, never by reading business rows. This is deliberately NOT
    the BYPASSRLS support-access path: it never touches row content, only
    COUNT(*), which is what "aggregate, anonymized usage data" means here."""
    tenants = db.query(Tenant).all()
    total_users = 0
    total_projects = 0
    for tenant in tenants:
        set_rls_context(db, tenant.id)
        total_users += (
            db.query(UserTenantRole)
            .filter(UserTenantRole.tenant_id == tenant.id, UserTenantRole.is_active.is_(True))
            .count()
        )
        total_projects += db.query(Project).filter(Project.tenant_id == tenant.id).count()

    return UsageSummary(
        tenant_count=len(tenants),
        active_tenant_count=sum(1 for t in tenants if t.status == TenantStatus.active),
        total_users=total_users,
        total_projects=total_projects,
    )


class SupportAccessRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=500)


class SupportAccessProjectSummary(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    activity_count: int


class SupportAccessResponse(BaseModel):
    tenant_id: uuid.UUID
    tenant_name: str
    projects: list[SupportAccessProjectSummary]


@router.post("/tenants/{tenant_id}/support-access", response_model=SupportAccessResponse)
def support_access(
    tenant_id: uuid.UUID,
    payload: SupportAccessRequest,
    request: Request,
    platform_admin: User = Depends(get_current_platform_admin),
    db: Session = Depends(get_db),
) -> SupportAccessResponse:
    """The one narrow, explicit, always-logged path that reads a tenant's
    business data as a platform admin. Uses the BYPASSRLS `poko_bypass`
    connection — never the ordinary `poko_app` session used everywhere else —
    and writes its own audit_logs row synchronously, in the same transaction as
    the read, so the log entry is guaranteed to exist if the query ran."""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    bypass_db = BypassSessionLocal()
    try:
        projects = bypass_db.query(Project).filter(Project.tenant_id == tenant_id).all()
        summaries = [
            SupportAccessProjectSummary(
                id=project.id,
                name=project.name,
                code=project.code,
                activity_count=bypass_db.query(Activity)
                .filter(Activity.project_id == project.id)
                .count(),
            )
            for project in projects
        ]
        audit.log_sync(
            bypass_db,
            "platform.support_access",
            tenant_id=tenant_id,
            actor_user_id=platform_admin.id,
            target_type="tenant",
            target_id=tenant_id,
            event_metadata={"reason": payload.reason, "endpoint": str(request.url.path)},
            ip_address=request.client.host if request.client else None,
        )
        bypass_db.commit()
    finally:
        bypass_db.close()

    return SupportAccessResponse(tenant_id=tenant.id, tenant_name=tenant.name, projects=summaries)


@router.post("/admins", response_model=PlatformAdminOut, status_code=status.HTTP_201_CREATED)
def create_platform_admin(
    payload: PlatformAdminCreate,
    db: Session = Depends(get_db),
    platform_admin: User = Depends(get_current_platform_admin),
) -> User:
    """Unlike tenant onboarding, this sets a password directly rather than
    emailing an invite — platform admins are internal POKO staff the creating
    admin already has an out-of-band way to hand credentials to."""
    email = payload.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        title=payload.title,
        phone=payload.phone,
        is_platform_admin=True,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit.log(
        "platform_admin.created", tenant_id=None, actor_user_id=platform_admin.id,
        target_type="user", target_id=user.id, event_metadata={"email": user.email},
    )
    return user


@router.get("/admins", response_model=list[PlatformAdminOut])
def list_platform_admins(
    db: Session = Depends(get_db), _: User = Depends(get_current_platform_admin)
) -> list[User]:
    return (
        db.query(User)
        .filter(User.is_platform_admin.is_(True))
        .order_by(User.created_at.asc())
        .all()
    )


@router.post("/admins/{admin_id}/deactivate", response_model=PlatformAdminOut)
def deactivate_platform_admin(
    admin_id: uuid.UUID,
    db: Session = Depends(get_db),
    platform_admin: User = Depends(get_current_platform_admin),
) -> User:
    if admin_id == platform_admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Can't deactivate your own access")
    target = db.query(User).filter(User.id == admin_id, User.is_platform_admin.is_(True)).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform admin not found")
    target.is_active = False
    db.commit()
    db.refresh(target)
    audit.log(
        "platform_admin.deactivated", tenant_id=None, actor_user_id=platform_admin.id,
        target_type="user", target_id=target.id,
    )
    return target


@router.post("/admins/{admin_id}/activate", response_model=PlatformAdminOut)
def activate_platform_admin(
    admin_id: uuid.UUID,
    db: Session = Depends(get_db),
    platform_admin: User = Depends(get_current_platform_admin),
) -> User:
    target = db.query(User).filter(User.id == admin_id, User.is_platform_admin.is_(True)).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform admin not found")
    if target.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admin is already active")
    target.is_active = True
    db.commit()
    db.refresh(target)
    audit.log(
        "platform_admin.activated", tenant_id=None, actor_user_id=platform_admin.id,
        target_type="user", target_id=target.id,
    )
    return target
