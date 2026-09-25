from pathlib import Path

from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_project.xer"


def _setup(db_session, slug):
    tenant = create_tenant(db_session, name="Acme", slug=slug)
    project = create_project(db_session, tenant)
    admin = create_user(db_session, f"{slug}@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project, f"{slug}@example.com"


def _login_and_import(client, db_session, slug):
    _tenant, project, email = _setup(db_session, slug)
    client.post("/auth/login", json={"email": email, "password": "secret123"})
    with open(FIXTURE, "rb") as f:
        upload = client.post(
            f"/projects/{project.id}/schedule-imports",
            files={"file": ("synthetic_project.xer", f.read(), "application/octet-stream")},
        )
    assert upload.status_code == 201
    return project


def test_float_paths_split_the_fixture_network_at_the_finish_milestone(client, db_session):
    # A100 → A200 → A300 → A600  (the long chain)
    # A100 → A400 → A500 → A600  (40h of float)
    project = _login_and_import(client, db_session, "fp-route-1")

    response = client.get(f"/projects/{project.id}/float-path?end_activity=A600&path_count=3")

    assert response.status_code == 200
    body = response.json()
    assert body["end_activity_external_id"] == "A600"
    assert body["end_activity_name"] == "Substantial Completion"

    paths = body["paths"]
    assert [[a["external_id"] for a in p["activities"]] for p in paths] == [
        ["A100", "A200", "A300", "A600"],
        ["A400", "A500"],
    ]
    assert paths[0]["total_float_days"] == 0.0
    # The second chain feeds the milestone directly; A100 is already spoken for.
    assert paths[1]["joins_at_external_id"] == "A600"
    # 40h of float read on the fixture's own 9h/day calendar, not a nominal 8.
    assert body["hours_per_day"] == 9.0
    assert paths[1]["total_float_days"] == 4.44
    # Pull the critical chain in by more than that and A400/A500 take over.
    assert body["acceleration_headroom_days"] == 4.44


def test_end_candidates_put_milestones_first(client, db_session):
    project = _login_and_import(client, db_session, "fp-route-2")

    response = client.get(f"/projects/{project.id}/float-path/end-candidates")

    assert response.status_code == 200
    rows = response.json()
    assert rows[0]["external_id"] == "A600"
    assert rows[0]["task_type"] == "TT_FinMile"
    assert {r["external_id"] for r in rows} == {"A100", "A200", "A300", "A400", "A500", "A600"}


def test_unknown_end_activity_is_a_404(client, db_session):
    project = _login_and_import(client, db_session, "fp-route-3")

    response = client.get(f"/projects/{project.id}/float-path?end_activity=NOPE")

    assert response.status_code == 404


def test_float_path_rejects_another_tenants_project(client, db_session):
    _tenant, _project, email = _setup(db_session, "fp-route-4")
    other_tenant = create_tenant(db_session, name="Other", slug="fp-route-4-other")
    other_project = create_project(db_session, other_tenant)
    client.post("/auth/login", json={"email": email, "password": "secret123"})

    response = client.get(f"/projects/{other_project.id}/float-path?end_activity=A600")

    assert response.status_code == 403
