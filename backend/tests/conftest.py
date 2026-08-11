import os

# All three DB URLs point at SQLite: this guarantees that if any code path
# (e.g. the platform support-access route) ever tries to open the bypass or
# migrate engine during a test, it fails fast against a schema-less in-memory
# DB instead of hanging on a real network connection to a Postgres that isn't
# running in this environment. RLS itself is Postgres-only and is exercised by
# a separate, explicitly-gated test module — not this suite.
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("DATABASE_URL_BYPASS", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("DATABASE_URL_MIGRATE", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ENV", "development")
os.environ.setdefault("REDIS_HOST", "localhost")

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (registers every model on Base.metadata)
from app.core.redis_client import get_redis
from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
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
