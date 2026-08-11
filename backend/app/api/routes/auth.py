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
from app.db.session import get_db
from app.deps import (
    TENANT_REFRESH_COOKIE,
    TENANT_SESSION_COOKIE,
    AuthContext,
    get_current_tenant_user,
)
from app.models.user import User
from app.models.user_tenant_role import UserTenantRole
from app.schemas.auth import LoginRequest
from app.schemas.user import UserOut
from app.services import audit
from app.services.tenant_session import issue_tenant_session

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


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

    membership = (
        db.query(UserTenantRole)
        .filter(UserTenantRole.user_id == user.id, UserTenantRole.is_active.is_(True))
        .order_by(UserTenantRole.created_at.asc())
        .first()
    )
    if membership is None:
        audit.log("login.failed", tenant_id=None, actor_user_id=user.id, ip_address=client_ip)
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
        is_active=ctx.user.is_active,
        tenant_id=ctx.tenant_id,
        role=ctx.role,
        scope_ids=ctx.scope_ids,
    )
