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


def test_import_rejects_a_cyclic_relationship_network(client, db_session):
    """A real P6 export with a circular dependency (CPM can't be run on it)
    must come back as a clear 400, not an unhandled 500 — this is the first
    real-world .xer this app ever imported to surface CpmCycleError going
    uncaught (see app/main.py's global exception handler for the other half
    of this fix)."""
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})

    text = FIXTURE.read_bytes().decode("utf-8")
    # A600 (1006) already depends on A300 (1003) and A500 (1005); adding
    # A100 (1001) -> depends on -> A600 closes the loop 1001->1002->1003->1006->1001.
    cyclic_bytes = (text + "%R\t7\t1001\tPROJ1\t1006\tPROJ1\tPR_FS\t0\n").encode("utf-8")

    response = client.post(
        f"/projects/{project.id}/schedule-imports",
        files={"file": ("cyclic.xer", cyclic_bytes, "application/octet-stream")},
    )

    assert response.status_code == 400
    assert "circular dependency" in response.json()["detail"].lower()
    # Nothing partially written — schedule() raises before any DB writes happen.
    assert client.get(f"/projects/{project.id}/schedule-imports").json() == []


def test_unexpected_import_error_returns_a_proper_500_with_cors_headers(client, db_session, monkeypatch):
    """Regression test for a real production symptom: an unhandled exception
    reaching the browser with no CORS headers at all, which shows up as a
    misleading "blocked by CORS policy" error instead of the real 500 — see
    app/main.py's catch_unhandled_exceptions middleware and the comment on
    why it has to be a plain middleware (added before CORSMiddleware), not an
    @app.exception_handler(Exception)."""
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "xer-admin@example.com", "password": "secret123"})

    def _boom(*args, **kwargs):
        raise RuntimeError("something truly unexpected")

    monkeypatch.setattr("app.api.routes.schedule_imports.import_xer", _boom)

    with open(FIXTURE, "rb") as f:
        response = client.post(
            f"/projects/{project.id}/schedule-imports",
            files={"file": ("synthetic_project.xer", f.read(), "application/octet-stream")},
            headers={"Origin": "http://localhost:3000"},
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
