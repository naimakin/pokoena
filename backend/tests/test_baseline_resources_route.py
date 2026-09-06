from pathlib import Path

from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user

RESOURCE_FIXTURE = Path(__file__).parent / "fixtures" / "resource_loaded_project.xer"
PLAIN_FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_project.xer"


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-bsl-rsrc")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "rsrc-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project


def _login(client):
    client.post("/auth/login", json={"email": "rsrc-admin@example.com", "password": "secret123"})


def _upload(client, project_id, path):
    return client.post(
        f"/projects/{project_id}/evm/baseline/program",
        files={"file": (path.name, path.read_bytes(), "application/octet-stream")},
    )


def test_frozen_resources_are_listed_with_budget_rollups(client, db_session):
    _tenant, project = _setup(db_session)
    _login(client)
    assert _upload(client, project.id, RESOURCE_FIXTURE).status_code == 201

    body = client.get(f"/projects/{project.id}/evm/baseline/resources").json()

    assert body["resource_count"] == 3
    assert body["labor_count"] == 2
    assert body["material_count"] == 1
    # R1: 8 + 40 + 16 = 64h, R2: 24 + 8 = 32h  → 96 budgeted labor hours
    assert body["total_budgeted_labor_hours"] == 96.0
    assert body["total_budgeted_cost"] == 14600.0

    crew_a = next(r for r in body["resources"] if r["rsrc_id"] == "R1")
    assert crew_a["budgeted_qty"] == 64.0
    assert crew_a["assignment_count"] == 3


def test_resources_survive_a_later_progress_programme_import(client, db_session):
    _tenant, project = _setup(db_session)
    _login(client)
    _upload(client, project.id, RESOURCE_FIXTURE)

    # A later update programme with no RSRC/TASKRSRC data would wipe the live
    # resources tables — the frozen baseline copy must be unaffected.
    client.post(
        f"/projects/{project.id}/schedule-imports",
        files={"file": ("update_1.xer", PLAIN_FIXTURE.read_bytes(), "application/octet-stream")},
    )

    body = client.get(f"/projects/{project.id}/evm/baseline/resources").json()
    assert body["resource_count"] == 3


def test_resources_requires_a_baseline(client, db_session):
    _tenant, project = _setup(db_session)
    _login(client)

    response = client.get(f"/projects/{project.id}/evm/baseline/resources")

    assert response.status_code == 423
