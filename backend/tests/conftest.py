import os

# All three DB URLs point at SQLite so nothing ever opens a real network
# connection to a Postgres that isn't running in this environment. The
# bypass engine's module-level SQLite `:memory:` DB (created from
# DATABASE_URL_BYPASS below) is schema-less and unused in practice — the
# `db_session` fixture below redirects every legitimate BypassSessionLocal()
# caller to the same per-test database as everything else instead, so this
# URL only matters as a safe fallback for any *other* code path that opens it
# without going through that redirect. RLS itself is Postgres-only and is
# exercised by a separate, explicitly-gated test module — not this suite.
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("DATABASE_URL_BYPASS", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("DATABASE_URL_MIGRATE", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ENV", "development")
os.environ.setdefault("REDIS_HOST", "localhost")

import fakeredis
import pytest
from sqlalchemy import create_engine, event
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (registers every model on Base.metadata)
from app.core.redis_client import get_redis
from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture()
def db_session(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite ignores foreign keys unless a connection explicitly turns them
    # on — real Postgres (production) always enforces them. Without this, an
    # insert-order bug that violates a real FK (e.g. a row referencing a
    # not-yet-flushed parent) passes every test here and only ever surfaces
    # in production; see xer_import.py's ScheduleImport-before-activities
    # ordering for exactly that bug.
    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    # A few code paths open BypassSessionLocal() directly instead of taking a
    # Session via Depends(get_db) — the RLS-bootstrap invite lookup in
    # services/invites.py, and the platform support-access route — so
    # overriding the get_db dependency alone (see the `client` fixture below)
    # doesn't reach them. Point every module that imported BypassSessionLocal
    # by name at this same test database instead of the schema-less
    # DATABASE_URL_BYPASS one above, so those paths exercise real behavior
    # (schema and shared data) rather than always failing on a missing table.
    monkeypatch.setattr("app.services.invites.BypassSessionLocal", testing_session_local)
    monkeypatch.setattr("app.api.routes.platform.BypassSessionLocal", testing_session_local)
    monkeypatch.setattr("app.api.routes.auth.BypassSessionLocal", testing_session_local)
    monkeypatch.setattr("app.services.email_change.BypassSessionLocal", testing_session_local)

    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def fake_redis():
    # Real fakeredis instance (not a Mock) so INCR/EXPIRE/SETEX/EXISTS behave
    # like actual Redis — rate limiting and refresh-token revocation are
    # exercised for real, just without needing a live Redis server.
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture()
def client(db_session, fake_redis):
    def _override_get_db():
        yield db_session

    def _override_get_redis():
        return fake_redis

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_redis] = _override_get_redis
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
