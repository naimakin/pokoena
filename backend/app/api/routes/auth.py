import uuid

import jwt
import redis
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.rate_limit import rate_limit
from app.core.redis_client import get_redis
from app.core.security import (
    TENANT_REFRESH,
    decode_token,
    is_refresh_token_revoked,
    revoke_refresh_token,
    verify_password,
)
from app.db.session import BypassSessionLocal, get_db, set_rls_context
from app.deps import (
    TENANT_REFRESH_COOKIE,
    TENANT_SESSION_COOKIE,
    AuthContext,
    get_current_tenant_user,
)
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.models.user_tenant_role import UserTenantRole
from app.schemas.auth import LoginRequest
from app.schemas.user import UserOut
from app.services import audit
from app.services.tenant_session import issue_tenant_session

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _active_tenant_id_for_user(user_id: uuid.UUID) -> uuid.UUID | None:
    """Which tenant(s) a user belongs to is exactly what RLS on
    user_tenant_roles needs already-known context to answer — a
    chicken-and-egg the ordinary RLS-bound session can't resolve at login,
    before any tenant is established yet. The caller has already verified
    the account's password by this point, so reading across tenants for
    this one user is safe — same reasoning as the platform support-access
    path and the invite-lookup bootstrap in services/invites.py."""
    bypass_db = BypassSessionLocal()
    try:
        row = (
            bypass_db.query(UserTenantRole.tenant_id)
            .filter(UserTenantRole.user_id == user_id, UserTenantRole.is_active.is_(True))
            .order_by(UserTenantRole.created_at.asc())
            .first()
        )
        return row[0] if row else None
    finally:
        bypass_db.close()


@router.post(
    "/login", response_model=UserOut, dependencies=[Depends(rate_limit("tenant_login", limit=10, window_seconds=60))]
)
def login(
    payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> UserOut:
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    client_ip = request.client.host if request.client else None

    if not user or not user.is_active or not user.hashed_password:
        audit.log("login.failed", tenant_id=None, actor_user_id=None, ip_address=client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not verify_password(payload.password, user.hashed_password):
        audit.log("login.failed", tenant_id=None, actor_user_id=user.id, ip_address=client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    tenant_id = _active_tenant_id_for_user(user.id)
    if tenant_id is None:
        audit.log("login.failed", tenant_id=None, actor_user_id=user.id, ip_address=client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No active tenant access")

    # Must be set before this — and every later — query on `db` this request
    # makes: user_tenant_roles has RLS FORCEd, so it (and every other
    # tenant-scoped table `issue_tenant_session` below touches) is invisible
    # to this session until its tenant context is set.
    set_rls_context(db, tenant_id)

    tenant = db.get(Tenant, tenant_id)
    if tenant is None or tenant.status != TenantStatus.active:
        audit.log("login.failed", tenant_id=tenant_id, actor_user_id=user.id, ip_address=client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="This company's account is not active")

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
        # Only reachable via an extremely unlikely race (revoked between the
        # two lookups above) — same response as the "no membership" case.
        audit.log("login.failed", tenant_id=tenant_id, actor_user_id=user.id, ip_address=client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No active tenant access")

    result = issue_tenant_session(response, db, user, membership)
    audit.log(
        "login.success", tenant_id=membership.tenant_id, actor_user_id=user.id, ip_address=client_ip
    )
    return result


@router.post("/refresh", response_model=UserOut)
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
) -> UserOut:
    token = request.cookies.get(TENANT_REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")

    if payload.get("token_type") != TENANT_REFRESH:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type for this route")
    if is_refresh_token_revoked(redis_client, payload["jti"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked")

    user = db.get(User, uuid.UUID(payload["sub"]))
    tenant_id = uuid.UUID(payload["tenant_id"])
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    # See get_current_tenant_user's identical comment: must be set before the
    # first RLS-protected query below, not after.
    set_rls_context(db, tenant_id)

    tenant = db.get(Tenant, tenant_id)
    if tenant is None or tenant.status != TenantStatus.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    # Rotation: this refresh token can't be used again.
    revoke_refresh_token(redis_client, payload["jti"], settings.jwt_refresh_expires_days * 86400)
    return issue_tenant_session(response, db, user, membership)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    redis_client: redis.Redis = Depends(get_redis),
) -> dict:
    refresh_token = request.cookies.get(TENANT_REFRESH_COOKIE)
    if refresh_token:
        try:
            payload = decode_token(refresh_token)
            revoke_refresh_token(redis_client, payload["jti"], settings.jwt_refresh_expires_days * 86400)
        except jwt.PyJWTError:
            pass
    response.delete_cookie(TENANT_SESSION_COOKIE, domain=settings.cookie_domain, path="/")
    response.delete_cookie(TENANT_REFRESH_COOKIE, domain=settings.cookie_domain, path="/auth")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(ctx: AuthContext = Depends(get_current_tenant_user)) -> UserOut:
    return UserOut(
        id=ctx.user.id,
        email=ctx.user.email,
        full_name=ctx.user.full_name,
        title=ctx.user.title,
        phone=ctx.user.phone,
        is_active=ctx.user.is_active,
        tenant_id=ctx.tenant_id,
        role=ctx.role,
        project_roles=ctx.project_roles,
        scope_ids=ctx.scope_ids,
    )
