"""Uploading a second, unrelated program (a different P6 project's .xer, with
its own root WBS id) must not leave the first program's WBS tree behind
forever — wbs_nodes is wholesale-replaced per import, same as relationships.
An earlier program's WBS still survives on its ScheduleImport.wbs_snapshot for
Planning > WBS's "view an earlier program" selector."""

import uuid
from pathlib import Path

from app.models.user_tenant_role import TenantRole
from app.models.wbs_node import WbsNode
from tests.factories import add_membership, create_project, create_tenant, create_user

PROGRAM_A = Path(__file__).parent / "fixtures" / "wbs_program_a.xer"
PROGRAM_B = Path(__file__).parent / "fixtures" / "wbs_program_b.xer"


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-wbs-switch-test")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "wbs-switch-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project


def _upload(client, project_id, fixture: Path):
    with open(fixture, "rb") as f:
        return client.post(
            f"/projects/{project_id}/schedule-imports",
            files={"file": (fixture.name, f.read(), "application/octet-stream")},
        )


def test_live_wbs_only_reflects_the_current_program(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "wbs-switch-admin@example.com", "password": "secret123"})
    _upload(client, project.id, PROGRAM_A)

    live = client.get(f"/projects/{project.id}/wbs-nodes").json()
    assert {n["wbs_id"] for n in live} == {"PROGA", "PROGA.1"}

    _upload(client, project.id, PROGRAM_B)

    live = client.get(f"/projects/{project.id}/wbs-nodes").json()
    assert {n["wbs_id"] for n in live} == {"PROGB", "PROGB.1"}
    root = next(n for n in live if n["wbs_id"] == "PROGB")
    assert root["total_activity_count"] == 2

    # Program A's rows are gone from the live table entirely.
    assert db_session.query(WbsNode).filter(WbsNode.wbs_id.in_(["PROGA", "PROGA.1"])).count() == 0


def test_an_earlier_programs_wbs_is_still_viewable_from_its_import(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "wbs-switch-admin@example.com", "password": "secret123"})
    a = _upload(client, project.id, PROGRAM_A).json()
    _upload(client, project.id, PROGRAM_B)

    response = client.get(f"/projects/{project.id}/schedule-imports/{a['id']}/wbs-nodes")

    assert response.status_code == 200
    body = response.json()
    assert {n["wbs_id"] for n in body} == {"PROGA", "PROGA.1"}
    root = next(n for n in body if n["wbs_id"] == "PROGA")
    child = next(n for n in body if n["wbs_id"] == "PROGA.1")
    assert root["total_activity_count"] == 1
    assert child["direct_activity_count"] == 1
    assert child["parent_wbs_id"] == "PROGA"
    assert root["depth"] == 0 and child["depth"] == 1
    # Deterministic, not a real DB row — same id on a second call.
    again = client.get(f"/projects/{project.id}/schedule-imports/{a['id']}/wbs-nodes").json()
    assert {n["id"] for n in again} == {n["id"] for n in body}


def test_manually_added_wbs_node_survives_a_program_switch(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "wbs-switch-admin@example.com", "password": "secret123"})
    _upload(client, project.id, PROGRAM_A)
    manual = client.post(f"/projects/{project.id}/wbs-nodes", json={"wbs_short_name": "EXTRA", "wbs_name": "Manually added"})
    assert manual.status_code == 201

    _upload(client, project.id, PROGRAM_B)

    live = {n["wbs_id"]: n for n in client.get(f"/projects/{project.id}/wbs-nodes").json()}
    assert manual.json()["wbs_id"] in live
    assert {"PROGA", "PROGA.1"} - set(live) == {"PROGA", "PROGA.1"}  # program A is gone
    assert "PROGB" in live


def test_wbs_nodes_by_import_404s_for_a_foreign_or_unknown_import(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "wbs-switch-admin@example.com", "password": "secret123"})
    _upload(client, project.id, PROGRAM_A)

    response = client.get(f"/projects/{project.id}/schedule-imports/{uuid.uuid4()}/wbs-nodes")

    assert response.status_code == 404


def test_activities_by_import_reconstructs_from_the_snapshot(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "wbs-switch-admin@example.com", "password": "secret123"})
    a = _upload(client, project.id, PROGRAM_A).json()
    _upload(client, project.id, PROGRAM_B)

    response = client.get(f"/projects/{project.id}/schedule-imports/{a['id']}/activities")

    assert response.status_code == 200
    body = response.json()
    assert {row["external_id"] for row in body} == {"A100"}
    row = body[0]
    assert row["wbs_path"] == "PROGA.1"
    assert row["status"] == "not_started"
    assert "id" in row and row["id"]
