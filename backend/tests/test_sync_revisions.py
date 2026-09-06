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


def _login(client, email):
    client.post("/auth/login", json={"email": email, "password": "secret123"})


def _import(client, project_id, name="upd.xer", roundtrip_from_export_id=None):
    data = {}
    if roundtrip_from_export_id is not None:
        data["roundtrip_from_export_id"] = str(roundtrip_from_export_id)
    return client.post(
        f"/projects/{project_id}/schedule-imports",
        files={"file": (name, FIXTURE.read_bytes(), "application/octet-stream")},
        data=data,
    )


def test_first_import_is_baseline_then_updates_are_numbered(client, db_session):
    _tenant, project, email = _setup(db_session, "sync-rev-1")
    _login(client, email)

    first = _import(client, project.id)
    assert first.status_code == 201
    assert first.json()["revision_label"] == "Baseline programme"
    assert first.json()["revision_no"] is None

    second = _import(client, project.id)
    assert second.json()["revision_label"] == "UPD-1"
    assert second.json()["revision_no"] == 1

    third = _import(client, project.id)
    assert third.json()["revision_label"] == "UPD-2"


def test_export_gets_sequential_label_and_filename(client, db_session):
    _tenant, project, email = _setup(db_session, "sync-rev-2")
    _login(client, email)
    _import(client, project.id)

    first = client.get(f"/projects/{project.id}/export/xer")
    assert first.headers["content-disposition"] == f'attachment; filename="{project.code}-EXP-1.xer"'
    second = client.get(f"/projects/{project.id}/export/xer")
    assert second.headers["content-disposition"] == f'attachment; filename="{project.code}-EXP-2.xer"'


def test_sync_log_merges_exports_and_imports(client, db_session):
    _tenant, project, email = _setup(db_session, "sync-rev-3")
    _login(client, email)
    _import(client, project.id)  # Baseline programme
    client.get(f"/projects/{project.id}/export/xer")  # EXP-1
    _import(client, project.id)  # UPD-1

    log = client.get(f"/projects/{project.id}/sync-log")
    assert log.status_code == 200
    rows = log.json()
    assert {(r["kind"], r["label"]) for r in rows} == {
        ("import", "Baseline programme"),
        ("export", "EXP-1"),
        ("import", "UPD-1"),
    }
    exp = next(r for r in rows if r["kind"] == "export")
    assert exp["filename"] == f"{project.code}-EXP-1.xer"
    assert exp["activity_count"] == 6


def test_import_can_be_linked_to_an_export_as_roundtrip(client, db_session):
    _tenant, project, email = _setup(db_session, "sync-rev-4")
    _login(client, email)
    _import(client, project.id)

    client.get(f"/projects/{project.id}/export/xer")
    # Export id isn't in the download response; read it from the sync log.
    exp_row = next(r for r in client.get(f"/projects/{project.id}/sync-log").json() if r["kind"] == "export")

    linked = _import(client, project.id, roundtrip_from_export_id=exp_row["id"])
    assert linked.status_code == 201
    assert linked.json()["roundtrip_from_export_id"] == exp_row["id"]

    upd_row = next(r for r in client.get(f"/projects/{project.id}/sync-log").json() if r["kind"] == "import" and r["label"] == "UPD-1")
    assert upd_row["linked_export_label"] == "EXP-1"


def test_roundtrip_link_to_unknown_export_is_rejected(client, db_session):
    _tenant, project, email = _setup(db_session, "sync-rev-5")
    _login(client, email)
    _import(client, project.id)

    bad = _import(client, project.id, roundtrip_from_export_id="00000000-0000-0000-0000-000000000000")
    assert bad.status_code == 400


def test_sync_log_rejects_other_tenant(client, db_session):
    _tenant, _project, email = _setup(db_session, "sync-rev-6")
    other_tenant = create_tenant(db_session, name="Other", slug="sync-rev-6-other")
    other_project = create_project(db_session, other_tenant)
    _login(client, email)

    assert client.get(f"/projects/{other_project.id}/sync-log").status_code == 403
