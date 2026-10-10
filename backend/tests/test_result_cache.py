"""The Redis result cache (app/core/cache.py): a repeat read is served from
Redis, and any committed write to the project throws it away."""

from pathlib import Path

from app.core import cache
from app.models.activity import Activity
from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user

RESOURCE_FIXTURE = Path(__file__).parent / "fixtures" / "resource_loaded_project.xer"


def _setup(client, db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-cache")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "cache-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    client.post("/auth/login", json={"email": "cache-admin@example.com", "password": "secret123"})
    res = client.post(
        f"/projects/{project.id}/evm/baseline/program",
        files={"file": (RESOURCE_FIXTURE.name, RESOURCE_FIXTURE.read_bytes(), "application/octet-stream")},
    )
    assert res.status_code == 201
    return tenant, project


def test_repeat_read_is_served_from_the_cache(client, db_session, monkeypatch):
    _, project = _setup(client, db_session)
    calls = []
    real = cache._dump
    monkeypatch.setattr(cache, "_dump", lambda result: calls.append(1) or real(result))

    first = client.get(f"/dashboard/analytics?project_id={project.id}")
    second = client.get(f"/dashboard/analytics?project_id={project.id}")

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert len(calls) == 1  # computed once, the second answer came from Redis


def test_a_committed_write_invalidates_the_project(client, db_session):
    _, project = _setup(client, db_session)
    before = client.get(f"/dashboard/analytics?project_id={project.id}").json()

    act = db_session.query(Activity).filter(Activity.project_id == project.id).first()
    act.name = "Renamed so the behind-plan rows would differ"
    act.percent_complete = 100
    db_session.commit()

    after = client.get(f"/dashboard/analytics?project_id={project.id}").json()
    assert after != before


def test_versions_are_per_project(_result_cache_redis, db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-cache-2")
    a = create_project(db_session, tenant, name="A", code="A")
    b = create_project(db_session, tenant, name="B", code="B")
    r = _result_cache_redis

    va = cache._versions(r, [f"p:{a.id}", f"p:{b.id}"])
    cache.bump(f"p:{a.id}")
    vb = cache._versions(r, [f"p:{a.id}", f"p:{b.id}"])

    assert va[0] != vb[0]  # A moved on
    assert va[1] == vb[1]  # B untouched


def test_a_rolled_back_write_bumps_nothing(_result_cache_redis, db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-cache-3")
    project = create_project(db_session, tenant)
    before = cache._versions(_result_cache_redis, [f"p:{project.id}"])

    project.name = "Never saved"
    db_session.flush()
    db_session.rollback()

    assert cache._versions(_result_cache_redis, [f"p:{project.id}"]) == before
