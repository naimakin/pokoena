import uuid
from dataclasses import dataclass, field
from typing import TypeVar

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.security import PLATFORM_ACCESS, TENANT_ACCESS, decode_token
from app.db.session import get_db, set_rls_context
from app.models.project_membership import ProjectMembership, ProjectPermission
from app.models.user import User
from app.models.user_tenant_role import TenantRole, UserTenantRole

TENANT_SESSION_COOKIE = "poko_tenant_session"
TENANT_REFRESH_COOKIE = "poko_tenant_refresh"
PLATFORM_SESSION_COOKIE = "poko_platform_session"
PLATFORM_REFRESH_COOKIE = "poko_platform_refresh"

ModelT = TypeVar("ModelT")


@dataclass
class AuthContext:
    """Everything a tenant-side route needs, resolved once per request."""

    user: User
    tenant_id: uuid.UUID
    role: TenantRole
    scope_ids: list[uuid.UUID] = field(default_factory=list)
    subcontractor_org_id: uuid.UUID | None = None


def _decode_cookie_token(request: Request, cookie_name: str) -> dict:
    token = request.cookies.get(cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        return decode_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")


def get_current_tenant_user(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    """Tenant-side auth: company_admin / company_employee / subcontractor.

    Deliberately a distinct dependency from `get_current_platform_admin` below
    (rather than one shared `get_current_user`) — the whole point of splitting
    token types is that a route only ever accepts one or the other, never
    either, and giving them different names makes that impossible to blur by
    accident at the call site.
    """
    payload = _decode_cookie_token(request, TENANT_SESSION_COOKIE)

    if payload.get("token_type") != TENANT_ACCESS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type for this route"
        )

    tenant_id_raw = payload.get("tenant_id")
    if not tenant_id_raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    tenant_id = uuid.UUID(tenant_id_raw)

    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    # Re-derived from the DB, not trusted from the token claim: a role change or
    # tenant-access revocation takes effect on the next request, not only after
    # the (short-lived) access token happens to expire.
    membership = (
        db.query(UserTenantRole)
        .filter(
            UserTenantRole.user_id == user.id,
            UserTenantRole.tenant_id == tenant_id,
            UserTenantRole.is_active.is_(True),
        )
        .first()
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="No active access to this tenant"
        )

    scope_ids = [uuid.UUID(s) for s in payload.get("scope_ids", [])]
    set_rls_context(db, tenant_id)
    return AuthContext(
        user=user,
        tenant_id=tenant_id,
        role=membership.role,
        scope_ids=scope_ids,
        subcontractor_org_id=membership.subcontractor_org_id,
    )


def get_current_platform_admin(request: Request, db: Session = Depends(get_db)) -> User:
    """Platform-side auth: POKO staff only. Deliberately never calls
    set_rls_context — a tenant-table query made by accident under this
    dependency sees zero rows (fail-closed) rather than every tenant's data.
    """
    payload = _decode_cookie_token(request, PLATFORM_SESSION_COOKIE)

    if payload.get("token_type") != PLATFORM_ACCESS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type for this route"
        )

    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active or not user.is_platform_admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    return user


def require_role(*roles: TenantRole):
    def _check(ctx: AuthContext = Depends(get_current_tenant_user)) -> AuthContext:
        if ctx.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted")
        return ctx

    return _check


def require_tenant_access(resource_tenant_id: uuid.UUID, ctx: AuthContext) -> None:
    """The core cross-tenant guard: 403s — never a distinct 404, which would
    leak whether the resource exists at all — when a resource's tenant_id
    doesn't match the caller's token. This is application-level defense in
    depth on top of Postgres RLS, not a substitute for it."""
    if resource_tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted")


def require_scope_access(project_scope_id: uuid.UUID | None, ctx: AuthContext) -> None:
    """Subcontractor guard: their token's scope_ids is the source of truth for
    which project_scopes they can touch. Checking the token (not re-querying
    subcontractor_scope_assignments) is deliberate — access tokens are
    short-lived (15 min), so a revoked assignment is stale for at most that
    long, and avoiding the extra query keeps every scoped route fast."""
    if ctx.role != TenantRole.subcontractor:
        return
    if project_scope_id is None or project_scope_id not in ctx.scope_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your scope")


def require_project_permission(
    db: Session, project_id: uuid.UUID, ctx: AuthContext, need_edit: bool = False
) -> None:
    """Company Admins have full tenant-wide project access. Company Employees
    need a ProjectMembership row for this specific project — and, if
    `need_edit`, one with edit (not view-only) permission — matching "sees
    only their own company's projects, view-only vs edit, per project."
    Subcontractors aren't gated by this at all: their access is scope-based
    (require_scope_access), not project-membership-based.
    """
    if ctx.role in (TenantRole.company_admin, TenantRole.subcontractor):
        return
    membership = (
        db.query(ProjectMembership)
        .filter(ProjectMembership.project_id == project_id, ProjectMembership.user_id == ctx.user.id)
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted for this project")
    if need_edit and membership.permission != ProjectPermission.edit:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="View-only access to this project")


def get_tenant_scoped_or_404(
    db: Session, model: type[ModelT], resource_id: uuid.UUID, ctx: AuthContext
) -> ModelT:
    """Loads any tenant-scoped row by id: 404s if it doesn't exist at all, 403s
    (via require_tenant_access) if it belongs to another tenant. This is the
    one reusable load-and-check nearly every resource route needs, instead of
    each route re-writing its own tenant comparison."""
    resource = db.get(model, resource_id)
    if resource is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"{model.__name__} not found"
        )
    require_tenant_access(resource.tenant_id, ctx)
    return resource
