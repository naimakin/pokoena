from pathlib import Path

from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_project.xer"


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-risk-test")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "risk-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project


def _import_fixture(client, project_id):
    with open(FIXTURE, "rb") as f:
        return client.post(
            f"/projects/{project_id}/schedule-imports",
            files={"file": ("synthetic_project.xer", f.read(), "application/octet-stream")},
        )


def test_monte_carlo_simulation_after_schedule_import(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "risk-admin@example.com", "password": "secret123"})
    assert _import_fixture(client, project.id).status_code == 201

    response = client.post(f"/projects/{project.id}/risk/monte-carlo", json={"iterations": 200, "spread": 0.25})

    assert response.status_code == 200
    body = response.json()
    assert body["iterations"] == 200
    assert body["project_finish_p10"] <= body["project_finish_p50"]
    assert body["project_finish_p50"] <= body["project_finish_p80"]
    assert body["project_finish_p80"] <= body["project_finish_p90"]
    assert len(body["histogram"]) > 0
    assert isinstance(body["critical_activities"], list)


def test_monte_carlo_rejects_empty_project(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "risk-admin@example.com", "password": "secret123"})

    response = client.post(f"/projects/{project.id}/risk/monte-carlo", json={})

    assert response.status_code == 400


def test_monte_carlo_rejects_invalid_override(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "risk-admin@example.com", "password": "secret123"})
    assert _import_fixture(client, project.id).status_code == 201

    activities = client.get(f"/activities?project_id={project.id}").json()
    target = activities[0]["id"]

    response = client.post(
        f"/projects/{project.id}/risk/monte-carlo",
        json={
            "overrides": [
                {"activity_id": target, "optimistic": 100.0, "most_likely": 50.0, "pessimistic": 10.0}
            ]
        },
    )

    assert response.status_code == 400


def test_monte_carlo_uses_default_iterations_when_omitted(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "risk-admin@example.com", "password": "secret123"})
    assert _import_fixture(client, project.id).status_code == 201

    response = client.post(f"/projects/{project.id}/risk/monte-carlo", json={})

    assert response.status_code == 200
    assert response.json()["iterations"] == 1000
