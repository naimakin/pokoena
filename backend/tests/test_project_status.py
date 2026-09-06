from pathlib import Path

from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_project.xer"


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-status-test")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "status-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project


def _login(client):
    client.post("/auth/login", json={"email": "status-admin@example.com", "password": "secret123"})


def _upload(client, project_id):
    with open(FIXTURE, "rb") as f:
        return client.post(
            f"/projects/{project_id}/schedule-imports",
            files={"file": ("synthetic_project.xer", f.read(), "application/octet-stream")},
        )


def test_status_empty_project(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)

    response = client.get(f"/projects/{project.id}/status")

    assert response.status_code == 200
    body = response.json()
    assert body["has_snapshots"] is False
    assert body["priorities"]["filtered_total"] == 0
    assert {q["key"] for q in body["priorities"]["quadrants"]} == {
        "focus",
        "watch",
        "delegate",
        "later",
    }
    assert all(q["program_count"] == 0 for q in body["priorities"]["quadrants"])


def test_status_after_import(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    assert _upload(client, project.id).status_code == 201

    body = client.get(f"/projects/{project.id}/status").json()

    # The import hook wrote a snapshot, so the trend has a real point.
    assert body["has_snapshots"] is True
    assert body["latest_revision_label"] == "Baseline programme"
    assert body["summary"]["quality"]["metric"] > 0
    # DCMA score is always computable, so the quality trend always has a point.
    assert len(body["summary"]["quality"]["series"]) >= 1
    for card in ("progress", "risk", "quality"):
        assert body["summary"][card]["verdict"]
        assert isinstance(body["summary"][card]["series"], list)

    # Every non-WBS/LOE imported activity lands in exactly one quadrant.
    quadrants = body["priorities"]["quadrants"]
    assert sum(q["program_count"] for q in quadrants) == body["priorities"]["filtered_total"]
    assert body["priorities"]["filtered_total"] == 6


def test_status_text_filter_narrows_results(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    _upload(client, project.id)

    all_rows = client.get(f"/projects/{project.id}/status").json()["priorities"]["filtered_total"]
    filtered = client.get(f"/projects/{project.id}/status", params={"q": "A100"}).json()

    assert filtered["priorities"]["filtered_total"] < all_rows
    assert sum(q["program_count"] for q in filtered["priorities"]["quadrants"]) == filtered[
        "priorities"
    ]["filtered_total"]


def test_status_trend_grows_with_each_update(client, db_session):
    tenant, project = _setup(db_session)
    _login(client)
    _upload(client, project.id)
    before = len(client.get(f"/projects/{project.id}/status").json()["summary"]["quality"]["series"])

    _upload(client, project.id)
    after = len(client.get(f"/projects/{project.id}/status").json()["summary"]["quality"]["series"])

    assert after == before + 1
