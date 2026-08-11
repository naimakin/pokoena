import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import redis

from app.core.config import get_settings

settings = get_settings()

TENANT_ACCESS = "tenant_access"
TENANT_REFRESH = "tenant_refresh"
PLATFORM_ACCESS = "platform_access"
PLATFORM_REFRESH = "platform_refresh"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def _encode(payload: dict) -> str:
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_tenant_access_token(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    role: str,
    scope_ids: list[uuid.UUID] | None = None,
) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_expires_minutes)
    return _encode(
        {
            "sub": str(user_id),
            "token_type": TENANT_ACCESS,
            "tenant_id": str(tenant_id),
            "role": role,
            "scope_ids": [str(s) for s in scope_ids] if scope_ids else [],
            "jti": str(uuid.uuid4()),
            "iat": datetime.now(timezone.utc),
            "exp": expires_at,
        }
    )


def create_tenant_refresh_token(user_id: uuid.UUID, tenant_id: uuid.UUID, jti: str | None = None) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_expires_days)
    return _encode(
        {
            "sub": str(user_id),
            "token_type": TENANT_REFRESH,
            "tenant_id": str(tenant_id),
            "jti": jti or str(uuid.uuid4()),
            "iat": datetime.now(timezone.utc),
            "exp": expires_at,
        }
    )


def create_platform_access_token(user_id: uuid.UUID) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_expires_minutes)
    return _encode(
        {
            "sub": str(user_id),
            "token_type": PLATFORM_ACCESS,
            "tenant_id": None,
            "role": None,
            "scope_ids": [],
            "jti": str(uuid.uuid4()),
            "iat": datetime.now(timezone.utc),
            "exp": expires_at,
        }
    )


def create_platform_refresh_token(user_id: uuid.UUID, jti: str | None = None) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_expires_days)
    return _encode(
        {
            "sub": str(user_id),
            "token_type": PLATFORM_REFRESH,
            "tenant_id": None,
            "jti": jti or str(uuid.uuid4()),
            "iat": datetime.now(timezone.utc),
            "exp": expires_at,
        }
    )


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


# Refresh tokens are stateless JWTs, but logout/rotation needs to actually revoke
# one rather than just wait out its (14 day) expiry — a Redis denylist keyed by
# `jti`, TTLed to the token's own remaining lifetime, gives us that cheaply.
# `redis_client` is passed in (rather than fetched internally) so callers get it
# via FastAPI's `Depends(get_redis)`, which tests can override with a fake.
def revoke_refresh_token(redis_client: redis.Redis, jti: str, expires_in_seconds: int) -> None:
    redis_client.setex(f"revoked_refresh:{jti}", max(expires_in_seconds, 1), "1")


def is_refresh_token_revoked(redis_client: redis.Redis, jti: str) -> bool:
    return redis_client.exists(f"revoked_refresh:{jti}") == 1
