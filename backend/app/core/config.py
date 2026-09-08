import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

# No-op if backend/.env doesn't exist (e.g. in prod, where config comes from
# Swarm secrets and the stack file's environment: block instead).
load_dotenv()


def _secret(name: str, default: str | None = None, required: bool = True) -> str | None:
    """Reads NAME_FILE (a Docker secret path) first, falling back to plain env var NAME.

    This lets the same settings code run under Docker Swarm secrets in production
    and plain .env values in local dev, without branching application logic.
    """
    file_path = os.getenv(f"{name}_FILE")
    if file_path:
        return Path(file_path).read_text(encoding="utf-8").strip()
    value = os.getenv(name, default)
    if required and value is None:
        raise RuntimeError(f"Missing required setting: {name} (or {name}_FILE)")
    return value


class Settings(BaseModel):
    env: str = os.getenv("ENV", "development")

    # Normal request path: RLS-bound `poko_app` role — every tenant-scoped query
    # this connection makes is filtered by the session's `app.current_tenant_id`.
    database_url: str = _secret(
        "DATABASE_URL", "postgresql+psycopg://poko_app:poko_app@localhost:5432/poko"
    )
    # Narrow, explicitly-audited path only: `poko_bypass` has BYPASSRLS. Never used
    # for ordinary request handling — see app/db/session.py and the platform
    # support-access route.
    database_url_bypass: str = _secret(
        "DATABASE_URL_BYPASS", "postgresql+psycopg://poko_bypass:poko_bypass@localhost:5432/poko"
    )
    # Alembic and one-off scripts (create_admin/seed_demo) run as the migration
    # owner, which needs CREATEROLE/table-owner privileges the two roles above
    # deliberately don't have.
    database_url_migrate: str = _secret(
        "DATABASE_URL_MIGRATE", "postgresql+psycopg://poko:poko@localhost:5432/poko"
    )

    jwt_secret: str = _secret("JWT_SECRET", "dev-insecure-secret-change-me")
    jwt_algorithm: str = "HS256"
    jwt_access_expires_minutes: int = int(os.getenv("JWT_ACCESS_EXPIRES_MINUTES", "60"))
    jwt_refresh_expires_days: int = int(os.getenv("JWT_REFRESH_EXPIRES_DAYS", "30"))

    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_password: str | None = _secret("REDIS_PASSWORD", None, required=False)

    # Base URL for links embedded in emails (invite-accept, etc.).
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:3000")

    cors_origins: list[str] = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    ]

    # Set to ".pokoena.com" in production so the auth cookie is shared between
    # pokoena.com and api.pokoena.com; left unset (host-only cookie) for local dev.
    cookie_domain: str | None = os.getenv("COOKIE_DOMAIN")


@lru_cache
def get_settings() -> Settings:
    return Settings()
