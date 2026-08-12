import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import BypassSessionLocal, get_db, set_rls_context
from app.deps import get_current_platform_admin
from app.models.activity import Activity
from app.models.project import Project
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.models.user_tenant_role import TenantRole, UserTenantRole
from app.schemas.tenant import TenantCreate, TenantOut, UsageSummary
from app.schemas.user import PlatformAdminCreate, PlatformAdminOut
from app.services import audit
from app.services.invites import create_invite

router = APIRouter(prefix="/platform", tags=["platform"])


@router.post("/tenants", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreate,
    db: Session = Depends(get_db),
    platform_admin: User = Depends(get_current_platform_admin),
) -> Tenant:
    if db.query(Tenant).filter(Tenant.slug == payload.slug).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already in use")

    tenant = Tenant(id=uuid.uuid4(), name=payload.name, slug=payload.slug, status=TenantStatus.active)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    create_invite(
        db=db,
        tenant_id=tenant.id,
        email=payload.admin_email,
        full_name=payload.admin_full_name,
        role=TenantRole.company_admin,
        invited_by_user_id=platform_admin.id,
        tenant_name=tenant.name,
    )
    audit.log(
        "tenant.created", tenant_id=tenant.id, actor_user_id=platform_admin.id,
        target_type="tenant", target_id=tenant.id, event_metadata={"name": tenant.name},
    )
    return tenant


@router.get("/tenants", response_model=list[TenantOut])
def list_tenants(
    db: Session = Depends(get_db), _: User = Depends(get_current_platform_admin)
) -> list[Tenant]:
    return db.query(Tenant).order_by(Tenant.created_at.desc()).all()


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
