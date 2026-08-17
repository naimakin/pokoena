from pathlib import Path

from app.models.activity import Activity
from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_project.xer"


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-xer-test")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "xer-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project


def _upload(client, project_id):
    with open(FIXTURE, "rb") as f:
        return client.post(
            f"/projects/{project_id}/schedule-imports",
            files={"file": ("synthetic_project.xer", f.read(), "application/octet-stream")},
        )


def test_upload_schedules_activities_and_returns_summary(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})

    response = _upload(client, project.id)

    assert response.status_code == 201
    body = response.json()
    assert body["activity_count"] == 6
    assert body["critical_count"] == 4
    assert body["filename"] == "synthetic_project.xer"


def test_activities_reflect_cpm_results_after_import(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})
    _upload(client, project.id)

    response = client.get(f"/activities?project_id={project.id}")
    assert response.status_code == 200
    by_code = {a["external_id"]: a for a in response.json()}

    assert set(by_code) == {"A100", "A200", "A300", "A400", "A500", "A600"}
    assert by_code["A300"]["is_critical"] is True
    assert by_code["A300"]["total_float_hours"] == 0
    assert by_code["A500"]["is_critical"] is False
    assert by_code["A500"]["total_float_hours"] == 40
    assert by_code["A200"]["early_start"] == "2026-01-05"
    assert by_code["A100"]["status"] == "not_started"
    assert by_code["A100"]["remaining_duration_days"] == 1


def test_reimport_preserves_subcontractor_owned_progress_fields(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})
    _upload(client, project.id)

    a100 = db_session.query(Activity).filter(Activity.project_id == project.id, Activity.external_id == "A100").one()
    patch_resp = client.patch(f"/activities/{a100.id}", json={"percent_complete": 40})
    assert patch_resp.status_code == 200

    _upload(client, project.id)

    db_session.expire_all()
    refreshed = db_session.query(Activity).filter(Activity.id == a100.id).one()
    assert refreshed.percent_complete == 40
    # P6-native fields still get overwritten by the re-import.
    assert refreshed.total_float_hours == 0


def test_history_endpoint_lists_past_imports(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})
    _upload(client, project.id)

    response = client.get(f"/projects/{project.id}/schedule-imports")
    assert response.status_code == 200
    imports = response.json()
    assert len(imports) == 1
    assert imports[0]["activity_count"] == 6


def test_rejects_non_xer_file(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})

    response = client.post(
        f"/projects/{project.id}/schedule-imports",
        files={"file": ("not-an-xer.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400
