import uuid

from fastapi import Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_tenant_access_token, create_tenant_refresh_token
from app.deps import TENANT_REFRESH_COOKIE, TENANT_SESSION_COOKIE
from app.models.subcontractor_scope_assignment import SubcontractorScopeAssignment
from app.models.user import User
from app.models.user_tenant_role import TenantRole, UserTenantRole
from app.schemas.user import UserOut

settings = get_settings()


def scope_ids_for(db: Session, user_id: uuid.UUID, tenant_id: uuid.UUID) -> list[uuid.UUID]:
    rows = (
        db.query(SubcontractorScopeAssignment.project_scope_id)
        .filter(
            SubcontractorScopeAssignment.user_id == user_id,
            SubcontractorScopeAssignment.tenant_id == tenant_id,
        )
        .all()
    )
    return [row[0] for row in rows]


def issue_tenant_session(
    response: Response, db: Session, user: User, membership: UserTenantRole
) -> UserOut:
    """Shared by /auth/login, /auth/refresh, and /invites/{token}/accept — every
    place a tenant-side session actually gets minted, so cookie shape and
    scope_ids resolution can't drift between them."""
    scope_ids = (
        scope_ids_for(db, user.id, membership.tenant_id)
        if membership.role == TenantRole.subcontractor
        else []
    )
    access_token = create_tenant_access_token(
        user_id=user.id, tenant_id=membership.tenant_id, role=membership.role.value, scope_ids=scope_ids
    )
    refresh_token = create_tenant_refresh_token(user_id=user.id, tenant_id=membership.tenant_id)

    is_prod = settings.env != "development"
    response.set_cookie(
        key=TENANT_SESSION_COOKIE,
        value=access_token,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        domain=settings.cookie_domain,
        max_age=settings.jwt_access_expires_minutes * 60,
        path="/",
    )
    response.set_cookie(
        key=TENANT_REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        domain=settings.cookie_domain,
        max_age=settings.jwt_refresh_expires_days * 86400,
        path="/auth",
    )

    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        title=user.title,
        phone=user.phone,
        is_active=user.is_active,
        tenant_id=membership.tenant_id,
        role=membership.role,
        project_role=membership.project_role,
        scope_ids=scope_ids,
    )
