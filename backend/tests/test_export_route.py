from pathlib import Path

from app.parser.xer_parser import parse_xer
from app.models.user import User
from app.models.user_tenant_role import TenantRole
from tests.factories import (
    add_membership,
    create_project,
    create_schedule_import,
    create_tenant,
    create_user,
)

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_project.xer"


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-export-test")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "export-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project


def test_export_with_no_activities_still_returns_valid_header(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "export-admin@example.com", "password": "secret123"})

    response = client.get(f"/projects/{project.id}/export/xer")

    assert response.status_code == 200
    assert response.content.startswith(b"ERMHDR")


def test_export_round_trips_the_synthetic_fixture(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "export-admin@example.com", "password": "secret123"})

    with open(FIXTURE, "rb") as f:
        upload = client.post(
            f"/projects/{project.id}/schedule-imports",
            files={"file": ("synthetic_project.xer", f.read(), "application/octet-stream")},
        )
    assert upload.status_code == 201

    response = client.get(f"/projects/{project.id}/export/xer")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == f'attachment; filename="{project.code}-EXP-1.xer"'

    reparsed = parse_xer(response.content)
    assert len(reparsed.activities) == 6
    assert len(reparsed.relationships) == 6
    by_code = {a.task_code: a for a in reparsed.activities}
    assert "A100" in by_code
    assert "A600" in by_code
    assert reparsed.meta.proj_id == "PROJ1"


def test_export_rejects_other_tenant(client, db_session):
    tenant, project = _setup(db_session)
    other_tenant = create_tenant(db_session, name="Other", slug="other-export-test")
    other_project = create_project(db_session, other_tenant)

    client.post("/auth/login", json={"email": "export-admin@example.com", "password": "secret123"})

    response = client.get(f"/projects/{other_project.id}/export/xer")

    assert response.status_code == 403


COMPLETED_FIXTURE = Path(__file__).parent / "fixtures" / "completed_not_critical.xer"


def _upload(client, project_id, path):
    return client.post(
        f"/projects/{project_id}/schedule-imports",
        files={"file": (path.name, path.read_bytes(), "application/octet-stream")},
    )


def _two_programmes(client, project_id):
    """Synthetic (data date 2026-01-05, A100…A600) as the baseline programme,
    then the completed fixture (2026-01-12, C100/C200) as the current update."""
    baseline = _upload(client, project_id, FIXTURE)
    current = _upload(client, project_id, COMPLETED_FIXTURE)
    assert baseline.status_code == 201 and current.status_code == 201
    return baseline.json(), current.json()


def test_export_defaults_to_the_current_programme(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "export-admin@example.com", "password": "secret123"})
    _baseline, current = _two_programmes(client, project.id)

    response = client.get(f"/projects/{project.id}/export/xer")

    assert response.status_code == 200
    assert {a.task_code for a in parse_xer(response.content).activities} == {"C100", "C200"}

    export_row = next(e for e in client.get(f"/projects/{project.id}/sync-log").json() if e["kind"] == "export")
    assert export_row["source_import_label"] == current["revision_label"]


def test_export_can_pick_an_earlier_programme(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "export-admin@example.com", "password": "secret123"})
    baseline, _current = _two_programmes(client, project.id)

    response = client.get(f"/projects/{project.id}/export/xer?import_id={baseline['id']}")

    assert response.status_code == 200
    # The chosen programme's own file goes out, not the live schedule's.
    assert {a.task_code for a in parse_xer(response.content).activities} == {
        "A100", "A200", "A300", "A400", "A500", "A600",
    }

    export_row = next(e for e in client.get(f"/projects/{project.id}/sync-log").json() if e["kind"] == "export")
    assert export_row["source_import_label"] == baseline["revision_label"]
    assert export_row["activity_count"] == 6


def test_export_rejects_a_programme_with_no_stored_file(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "export-admin@example.com", "password": "secret123"})
    _two_programmes(client, project.id)
    admin = db_session.query(User).filter(User.email == "export-admin@example.com").one()
    legacy = create_schedule_import(db_session, tenant, project, admin, revision_label="UPD-legacy")

    response = client.get(f"/projects/{project.id}/export/xer?import_id={legacy.id}")

    assert response.status_code == 400


def test_export_rejects_a_programme_from_another_project(client, db_session):
    tenant, project = _setup(db_session)
    other = create_project(db_session, tenant, name="Other project", code="OTHER")
    client.post("/auth/login", json={"email": "export-admin@example.com", "password": "secret123"})
    _two_programmes(client, other.id)
    other_import = client.get(f"/projects/{other.id}/schedule-imports").json()[0]

    response = client.get(f"/projects/{project.id}/export/xer?import_id={other_import['id']}")

    assert response.status_code == 404
