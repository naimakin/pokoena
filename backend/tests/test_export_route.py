from pathlib import Path

from app.parser.xer_parser import parse_xer
from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user

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
