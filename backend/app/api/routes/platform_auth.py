import uuid

import jwt
import redis
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.rate_limit import rate_limit
from app.core.redis_client import get_redis
from app.core.security import (
    PLATFORM_REFRESH,
    create_platform_access_token,
    create_platform_refresh_token,
    decode_token,
    is_refresh_token_revoked,
    revoke_refresh_token,
    verify_password,
)
from app.db.session import get_db
from app.deps import PLATFORM_REFRESH_COOKIE, PLATFORM_SESSION_COOKIE, get_current_platform_admin
from app.models.user import User
from app.schemas.auth import LoginRequest
from app.schemas.user import PlatformAdminOut
from app.services import audit

router = APIRouter(prefix="/platform-auth", tags=["platform-auth"])
settings = get_settings()


def _issue_platform_session(response: Response, user: User) -> PlatformAdminOut:
    access_token = create_platform_access_token(user_id=user.id)
    refresh_token = create_platform_refresh_token(user_id=user.id)

    is_prod = settings.env != "development"
    response.set_cookie(
        key=PLATFORM_SESSION_COOKIE,
        value=access_token,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        domain=settings.cookie_domain,
        max_age=settings.jwt_access_expires_minutes * 60,
        path="/",
    )
    response.set_cookie(
        key=PLATFORM_REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        domain=settings.cookie_domain,
        max_age=settings.jwt_refresh_expires_days * 86400,
        path="/platform-auth",
    )
    return PlatformAdminOut.model_validate(user)


@router.post(
    "/login",
    response_model=PlatformAdminOut,
    dependencies=[Depends(rate_limit("platform_login", limit=10, window_seconds=60))],
)
def login(
    payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> PlatformAdminOut:
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    client_ip = request.client.host if request.client else None

    valid = (
        user is not None
        and user.is_active
        and user.is_platform_admin
        and user.hashed_password
        and verify_password(payload.password, user.hashed_password)
    )
    if not valid:
        audit.log(
            "platform.login.failed",
            tenant_id=None,
            actor_user_id=user.id if user else None,
            ip_address=client_ip,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    result = _issue_platform_session(response, user)
    audit.log("platform.login.success", tenant_id=None, actor_user_id=user.id, ip_address=client_ip)
    return result


@router.post("/refresh", response_model=PlatformAdminOut)
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
) -> PlatformAdminOut:
    token = request.cookies.get(PLATFORM_REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")

    if payload.get("token_type") != PLATFORM_REFRESH:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type for this route")
    if is_refresh_token_revoked(redis_client, payload["jti"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked")

    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active or not user.is_platform_admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    revoke_refresh_token(redis_client, payload["jti"], settings.jwt_refresh_expires_days * 86400)
    return _issue_platform_session(response, user)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    redis_client: redis.Redis = Depends(get_redis),
) -> dict:
    refresh_token = request.cookies.get(PLATFORM_REFRESH_COOKIE)
    if refresh_token:
        try:
            payload = decode_token(refresh_token)
            revoke_refresh_token(redis_client, payload["jti"], settings.jwt_refresh_expires_days * 86400)
        except jwt.PyJWTError:
            pass
    response.delete_cookie(PLATFORM_SESSION_COOKIE, domain=settings.cookie_domain, path="/")
    response.delete_cookie(PLATFORM_REFRESH_COOKIE, domain=settings.cookie_domain, path="/platform-auth")
    return {"ok": True}


@router.get("/me", response_model=PlatformAdminOut)
def me(user: User = Depends(get_current_platform_admin)) -> User:
    return user
