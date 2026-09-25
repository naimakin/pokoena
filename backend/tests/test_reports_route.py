from pathlib import Path

from app.api.routes.reports import BLOCK_KEYS, PRESETS
from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_project.xer"


def _setup(db_session, slug):
    tenant = create_tenant(db_session, name="Acme", slug=slug)
    project = create_project(db_session, tenant)
    admin = create_user(db_session, f"{slug}@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project, f"{slug}@example.com"


def _login(client, db_session, slug):
    _tenant, project, email = _setup(db_session, slug)
    client.post("/auth/login", json={"email": email, "password": "secret123"})
    return project


def test_the_four_standard_formats_are_seeded_on_first_read(client, db_session):
    project = _login(client, db_session, "rep-1")

    response = client.get(f"/projects/{project.id}/report-formats")

    assert response.status_code == 200
    rows = response.json()
    assert [r["name"] for r in rows if r["is_preset"]] == sorted(p["name"] for p in PRESETS)
    monthly = next(r for r in rows if r["name"] == "Monthly Progress Report")
    enabled = [b["key"] for b in monthly["blocks"] if b["enabled"]]
    assert enabled[:3] == ["cover", "executive-summary", "milestones"]


def test_seeding_is_idempotent(client, db_session):
    project = _login(client, db_session, "rep-2")

    first = client.get(f"/projects/{project.id}/report-formats").json()
    second = client.get(f"/projects/{project.id}/report-formats").json()

    assert len(first) == len(second) == len(PRESETS)


def test_every_catalogue_block_appears_on_a_format_even_when_unselected(client, db_session):
    project = _login(client, db_session, "rep-3")

    rows = client.get(f"/projects/{project.id}/report-formats").json()
    exec_summary = next(r for r in rows if r["name"] == "Executive Summary")

    # The builder needs the full catalogue to offer, with the unpicked ones off.
    assert {b["key"] for b in exec_summary["blocks"]} == set(BLOCK_KEYS)
    assert not exec_summary["blocks"][0]["key"] == "dcma"
    assert next(b for b in exec_summary["blocks"] if b["key"] == "dcma")["enabled"] is False


def test_a_format_can_be_created_renamed_and_deleted(client, db_session):
    project = _login(client, db_session, "rep-4")

    created = client.post(
        f"/projects/{project.id}/report-formats",
        json={
            "name": "Weekly site pack",
            "description": "For the Monday meeting",
            "blocks": [{"key": "lookahead", "order": 0, "enabled": True, "options": {"weeks": 2}}],
        },
    )
    assert created.status_code == 201
    format_id = created.json()["id"]
    assert created.json()["is_preset"] is False

    renamed = client.patch(
        f"/projects/{project.id}/report-formats/{format_id}", json={"name": "Weekly site pack v2"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Weekly site pack v2"

    assert client.delete(f"/projects/{project.id}/report-formats/{format_id}").status_code == 204
    names = [r["name"] for r in client.get(f"/projects/{project.id}/report-formats").json()]
    assert "Weekly site pack v2" not in names


def test_duplicate_format_names_are_rejected(client, db_session):
    project = _login(client, db_session, "rep-5")
    body = {"name": "Same name", "blocks": []}

    assert client.post(f"/projects/{project.id}/report-formats", json=body).status_code == 201
    assert client.post(f"/projects/{project.id}/report-formats", json=body).status_code == 400


def test_an_unknown_block_key_is_rejected(client, db_session):
    project = _login(client, db_session, "rep-6")
    created = client.post(f"/projects/{project.id}/report-formats", json={"name": "F", "blocks": []}).json()

    response = client.patch(
        f"/projects/{project.id}/report-formats/{created['id']}",
        json={"blocks": [{"key": "not-a-block", "order": 0, "enabled": True, "options": {}}]},
    )

    assert response.status_code == 400
    assert "not-a-block" in response.json()["detail"]


def test_report_header_carries_the_provenance_a_report_is_judged_on(client, db_session):
    project = _login(client, db_session, "rep-7")
    with open(FIXTURE, "rb") as f:
        client.post(
            f"/projects/{project.id}/schedule-imports",
            files={"file": ("synthetic_project.xer", f.read(), "application/octet-stream")},
        )

    response = client.get(f"/projects/{project.id}/report-header")

    assert response.status_code == 200
    body = response.json()
    assert body["project_name"] == project.name
    assert body["project_code"] == project.code
    assert body["schedule_revision"] == "Baseline programme"
    assert body["schedule_filename"] == "synthetic_project.xer"
    assert body["data_date"] is not None
    assert "Duration-weighted" in body["progress_basis"]
    assert body["generated_by"]


def test_formats_are_not_visible_to_another_tenant(client, db_session):
    _tenant, _project, email = _setup(db_session, "rep-8")
    other_tenant = create_tenant(db_session, name="Other", slug="rep-8-other")
    other_project = create_project(db_session, other_tenant)
    client.post("/auth/login", json={"email": email, "password": "secret123"})

    assert client.get(f"/projects/{other_project.id}/report-formats").status_code == 403
    assert client.get(f"/projects/{other_project.id}/report-header").status_code == 403
