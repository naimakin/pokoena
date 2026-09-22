"""A project can already have two unrelated programs' WBS trees mixed live
(accumulated before wholesale-replace-per-import existed — see
test_wbs_program_switch.py) with no stored record of which root belonged to
which import, so there's nothing to prune automatically. Hiding a root is the
human escape hatch: reversible, no data deleted."""

from pathlib import Path

from app.models.user_tenant_role import TenantRole
from app.models.wbs_node import WbsNode
from tests.factories import add_membership, create_project, create_tenant, create_user
from tests.test_wbs_route import _activity

PROGRAM_A = Path(__file__).parent / "fixtures" / "wbs_program_a.xer"


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-wbs-hide-test")
    project = create_project(db_session, tenant)
    admin = create_user(db_session, "wbs-hide-admin@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, project


def _upload(client, project_id, fixture: Path):
    with open(fixture, "rb") as f:
        return client.post(
            f"/projects/{project_id}/schedule-imports",
            files={"file": (fixture.name, f.read(), "application/octet-stream")},
        )


def _root(db_session, project_id, wbs_id="PROGA") -> WbsNode:
    return db_session.query(WbsNode).filter(WbsNode.project_id == project_id, WbsNode.wbs_id == wbs_id).one()


def test_a_root_can_be_hidden_and_unhidden_without_deleting_anything(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "wbs-hide-admin@example.com", "password": "secret123"})
    _upload(client, project.id, PROGRAM_A)
    root_row = _root(db_session, project.id)

    hide_resp = client.post(f"/projects/{project.id}/wbs-nodes/{root_row.id}/hide")
    assert hide_resp.status_code == 200

    live_after = {n["wbs_id"] for n in client.get(f"/projects/{project.id}/wbs-nodes").json()}
    assert "PROGA" not in live_after and "PROGA.1" not in live_after
    # Nothing was deleted.
    assert db_session.query(WbsNode).filter(WbsNode.wbs_id.in_(["PROGA", "PROGA.1"])).count() == 2

    hidden = client.get(f"/projects/{project.id}/wbs-nodes/hidden").json()
    assert [n["wbs_id"] for n in hidden] == ["PROGA"]

    unhide_resp = client.post(f"/projects/{project.id}/wbs-nodes/{root_row.id}/unhide")
    assert unhide_resp.status_code == 200
    live_restored = {n["wbs_id"] for n in client.get(f"/projects/{project.id}/wbs-nodes").json()}
    assert {"PROGA", "PROGA.1"} <= live_restored
    assert client.get(f"/projects/{project.id}/wbs-nodes/hidden").json() == []


def test_hiding_a_root_removes_its_activities_from_the_page_total(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "wbs-hide-admin@example.com", "password": "secret123"})
    _upload(client, project.id, PROGRAM_A)  # 1 activity under PROGA.1
    _activity(db_session, tenant, project, "STALE-1", "PROGA.1")
    db_session.commit()

    before = next(n for n in client.get(f"/projects/{project.id}/wbs-nodes").json() if n["wbs_id"] == "PROGA")
    assert before["total_activity_count"] == 2  # A100 (from the import) + STALE-1

    root_row = _root(db_session, project.id)
    client.post(f"/projects/{project.id}/wbs-nodes/{root_row.id}/hide")

    after = client.get(f"/projects/{project.id}/wbs-nodes").json()
    assert "PROGA" not in {n["wbs_id"] for n in after}


def test_only_a_top_level_node_can_be_hidden(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "wbs-hide-admin@example.com", "password": "secret123"})
    _upload(client, project.id, PROGRAM_A)
    child = _root(db_session, project.id, "PROGA.1")

    response = client.post(f"/projects/{project.id}/wbs-nodes/{child.id}/hide")

    assert response.status_code == 400


def test_hidden_flag_survives_a_reimport_of_the_same_program(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "wbs-hide-admin@example.com", "password": "secret123"})
    _upload(client, project.id, PROGRAM_A)
    root_row = _root(db_session, project.id)
    client.post(f"/projects/{project.id}/wbs-nodes/{root_row.id}/hide")

    _upload(client, project.id, PROGRAM_A)  # re-upload the same program (upsert path, not delete+recreate)

    live = {n["wbs_id"] for n in client.get(f"/projects/{project.id}/wbs-nodes").json()}
    assert "PROGA" not in live  # still hidden
    db_session.expire_all()
    assert _root(db_session, project.id).is_hidden is True
