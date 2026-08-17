from pathlib import Path

from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_project.xer"


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-wbs-test")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "wbs-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project


def test_wbs_nodes_empty_before_import(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "wbs-admin@example.com", "password": "secret123"})

    response = client.get(f"/projects/{project.id}/wbs-nodes")

    assert response.status_code == 200
    assert response.json() == []


def test_wbs_nodes_after_import_with_no_projwbs_table(client, db_session):
    # The Slice 1 synthetic fixture has no PROJWBS block (activities reference
    # "WBS1" via TASK.wbs_id, but nothing defines that node) — parse_xer's
    # _parse_wbs reads only PROJWBS, so this import legitimately yields zero
    # WbsNode rows. Covered separately (with a real PROJWBS block) by
    # test_xer_writer.py's round-trip test.
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "wbs-admin@example.com", "password": "secret123"})

    with open(FIXTURE, "rb") as f:
        upload = client.post(
            f"/projects/{project.id}/schedule-imports",
            files={"file": ("synthetic_project.xer", f.read(), "application/octet-stream")},
        )
    assert upload.status_code == 201

    response = client.get(f"/projects/{project.id}/wbs-nodes")

    assert response.status_code == 200
    assert response.json() == []
