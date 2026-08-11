import uuid
from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# Normal request path — RLS-bound `poko_app` role.
engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# Platform support-access path only — `poko_bypass` role (BYPASSRLS). Never used
# for ordinary request handling; see app/deps.py and the platform support-access
# route for the one narrow, audited code path allowed to open this session.
bypass_engine = create_engine(settings.database_url_bypass, pool_pre_ping=True, future=True)
BypassSessionLocal = sessionmaker(bind=bypass_engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def set_rls_context(db: Session, tenant_id: uuid.UUID | None) -> None:
    """Sets `app.current_tenant_id` for the rest of this session, so every RLS
    policy on a tenant-scoped table applies automatically. Uses `set_config`
    (not string-built `SET LOCAL ...`) so the tenant id is a bound parameter,
    never interpolated into SQL.

    `SET LOCAL` (the `true` third arg) is transaction-scoped, not
    session-scoped — it resets itself the moment the current transaction
    commits. A single request routinely does query → commit → refresh, which
    starts a *new* transaction after the commit, and that new transaction
    would otherwise carry no tenant context at all, causing RLS to hide the
    very row the request just wrote. The `after_begin` listener below re-applies
    the same value on every subsequent transaction this session opens, so this
    only needs to be called once per request (typically from
    get_current_tenant_user) rather than after every commit.

    No-ops on non-Postgres engines (the pytest suite runs against SQLite): those
    tests exercise the application-level tenant checks instead, which is the
    layer RLS is a backstop for, not a replacement of.
    """
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    db.info["tenant_id"] = str(tenant_id) if tenant_id else ""
    db.execute(
        text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
        {"tenant_id": db.info["tenant_id"]},
    )


@event.listens_for(Session, "after_begin")
def _reapply_rls_context_on_new_transaction(session: Session, transaction, connection) -> None:
    """Companion to set_rls_context: fires every time this session begins a new
    transaction (including implicitly, right after a commit) and, if this
    session ever had a tenant context set, re-applies it immediately — so RLS
    stays in effect across the query → commit → refresh pattern most write
    routes use, without every route having to remember to re-set it."""
    tenant_id = session.info.get("tenant_id")
    if tenant_id is not None and connection.dialect.name == "postgresql":
        connection.execute(
            text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
            {"tenant_id": tenant_id},
        )
