import uuid
from pathlib import Path

from app.models.schedule_import import ScheduleImport
from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_project.xer"


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-diff-test")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "diff-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project


def _upload(client, project_id, file_bytes: bytes):
    return client.post(
        f"/projects/{project_id}/schedule-imports",
        files={"file": ("synthetic_project.xer", file_bytes, "application/octet-stream")},
    )


def _with_modified_lag(original: bytes) -> bytes:
    """Bump the A300-predecessor-A200 relationship's lag from 0h to 16h — a
    TASKPRED row `%R\t2\t1003\tPROJ1\t1002\tPROJ1\tPR_FS\t0` becomes ...\t16."""
    text = original.decode("utf-8")
    line = "%R\t2\t1003\tPROJ1\t1002\tPROJ1\tPR_FS\t0"
    assert line in text, "fixture TASKPRED row not found — fixture format changed?"
    return text.replace(line, "%R\t2\t1003\tPROJ1\t1002\tPROJ1\tPR_FS\t16").encode("utf-8")


def test_diffing_an_import_against_itself_reports_no_changes(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "diff-admin@example.com", "password": "secret123"})

    original = FIXTURE.read_bytes()
    first = _upload(client, project.id, original)
    second = _upload(client, project.id, original)
    assert first.status_code == 201 and second.status_code == 201

    response = client.get(
        f"/projects/{project.id}/logic-diff"
        f"?from_import_id={first.json()['id']}&to_import_id={second.json()['id']}"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {"added": 0, "removed": 0, "modified": 0, "total": 0}
    assert body["changes"] == []


def test_diff_detects_a_lag_change_between_imports(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "diff-admin@example.com", "password": "secret123"})

    original = FIXTURE.read_bytes()
    first = _upload(client, project.id, original)
    second = _upload(client, project.id, _with_modified_lag(original))
    assert first.status_code == 201 and second.status_code == 201

    response = client.get(
        f"/projects/{project.id}/logic-diff"
        f"?from_import_id={first.json()['id']}&to_import_id={second.json()['id']}"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["modified"] == 1
    change = body["changes"][0]
    assert change["pred_external_id"] == "A200"
    assert change["succ_external_id"] == "A300"
    assert change["changes"] == ["LAG_CHANGED"]
    assert change["old_lag_hours"] == 0.0
    assert change["new_lag_hours"] == 16.0


def test_diff_rejects_import_from_another_project(client, db_session):
    tenant, project_a = _setup(db_session)
    project_b = create_project(db_session, tenant, name="Other Project")
    client.post("/auth/login", json={"email": "diff-admin@example.com", "password": "secret123"})

    original = FIXTURE.read_bytes()
    in_a = _upload(client, project_a.id, original)
    in_b = _upload(client, project_b.id, original)
    assert in_a.status_code == 201 and in_b.status_code == 201

    response = client.get(
        f"/projects/{project_a.id}/logic-diff"
        f"?from_import_id={in_a.json()['id']}&to_import_id={in_b.json()['id']}"
    )

    assert response.status_code == 400


def test_relationships_snapshot_persisted_on_schedule_import_row(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "diff-admin@example.com", "password": "secret123"})

    upload = _upload(client, project.id, FIXTURE.read_bytes())
    assert upload.status_code == 201

    row = db_session.query(ScheduleImport).filter(ScheduleImport.id == uuid.UUID(upload.json()["id"])).one()
    assert len(row.relationships_snapshot) == 6
    codes = {(r["pred_external_id"], r["succ_external_id"]) for r in row.relationships_snapshot}
    assert ("A100", "A200") in codes
    assert ("A300", "A600") in codes
