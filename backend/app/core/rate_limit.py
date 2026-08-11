from collections.abc import Callable

import redis
from fastapi import Depends, HTTPException, Request, status

from app.core.redis_client import get_redis


def rate_limit(bucket: str, limit: int, window_seconds: int) -> Callable[..., None]:
    """Redis fixed-window rate limiter dependency, keyed by client IP. Applied to
    login and invite-acceptance endpoints to slow down credential/token guessing.

    Takes its Redis client via `Depends(get_redis)` (rather than calling
    `get_redis()` directly) so tests can override it with a fake in-memory client
    instead of needing a real Redis server."""

    def _dependency(request: Request, redis_client: redis.Redis = Depends(get_redis)) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"ratelimit:{bucket}:{client_ip}"
        current = redis_client.incr(key)
        if current == 1:
            redis_client.expire(key, window_seconds)
        if current > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts — please wait and try again.",
            )

    return _dependency
