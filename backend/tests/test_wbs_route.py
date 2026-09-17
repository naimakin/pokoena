import uuid
from pathlib import Path

from app.models.activity import Activity, ActivityStatus
from app.models.user_tenant_role import TenantRole
from app.models.wbs_node import WbsNode
from tests.factories import add_membership, create_project, create_tenant, create_user

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_project.xer"


def _wbs(db, tenant, project, wbs_id, parent, name, seq):
    node = WbsNode(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        project_id=project.id,
        wbs_id=wbs_id,
        parent_wbs_id=parent,
        wbs_short_name=name,
        wbs_name=name,
        seq_num=seq,
    )
    db.add(node)
    return node


def _activity(db, tenant, project, external_id, wbs_path):
    db.add(
        Activity(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            project_id=project.id,
            external_id=external_id,
            name=external_id,
            discipline="General",
            percent_complete=0,
            remaining_duration_days=1,
            status=ActivityStatus.not_started,
            wbs_path=wbs_path,
        )
    )


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


def test_wbs_tree_rollup_activity_counts(client, db_session):
    tenant, project = _setup(db_session)
    # root → construction → grinding ; root also has a direct milestones child
    _wbs(db_session, tenant, project, "R", None, "Project", 1)
    _wbs(db_session, tenant, project, "C", "R", "Construction", 2)
    _wbs(db_session, tenant, project, "G", "C", "Grinding", 3)
    _wbs(db_session, tenant, project, "M", "R", "Milestones", 4)
    _activity(db_session, tenant, project, "A1", "G")
    _activity(db_session, tenant, project, "A2", "G")
    _activity(db_session, tenant, project, "A3", "C")
    _activity(db_session, tenant, project, "A4", "M")
    db_session.commit()

    client.post("/auth/login", json={"email": "wbs-admin@example.com", "password": "secret123"})
    rows = {r["wbs_id"]: r for r in client.get(f"/projects/{project.id}/wbs-nodes").json()}

    assert rows["G"]["direct_activity_count"] == 2
    assert rows["G"]["total_activity_count"] == 2
    assert rows["C"]["direct_activity_count"] == 1
    assert rows["C"]["total_activity_count"] == 3  # 1 direct + 2 under Grinding
    assert rows["M"]["total_activity_count"] == 1
    assert rows["R"]["total_activity_count"] == 4  # everything
    # preorder (depth-first), not flat seq_num
    assert [r["wbs_id"] for r in client.get(f"/projects/{project.id}/wbs-nodes").json()] == ["R", "C", "G", "M"]
    # hierarchy metadata for the indented register
    assert rows["R"]["depth"] == 0 and rows["C"]["depth"] == 1 and rows["G"]["depth"] == 2
    assert rows["M"]["depth"] == 1
    assert rows["G"]["path_ids"] == ["R", "C", "G"]
    # short names here are prose ("Construction"), so outline codes are positional
    assert rows["R"]["outline_code"] == "1"
    assert rows["C"]["outline_code"] == "1.1"
    assert rows["G"]["outline_code"] == "1.1.1"
    assert rows["M"]["outline_code"] == "1.2"


def test_wbs_node_with_out_of_tree_parent_is_treated_as_root(client, db_session):
    tenant, project = _setup(db_session)
    # parent_wbs_id "GHOST" isn't in the project's node set (e.g. the P6 project
    # root node wasn't exported) — the node must still appear and still roll up.
    _wbs(db_session, tenant, project, "X", "GHOST", "Orphan branch", 1)
    _wbs(db_session, tenant, project, "Y", "X", "Child", 2)
    _activity(db_session, tenant, project, "A1", "Y")
    db_session.commit()

    client.post("/auth/login", json={"email": "wbs-admin@example.com", "password": "secret123"})
    rows = {r["wbs_id"]: r for r in client.get(f"/projects/{project.id}/wbs-nodes").json()}

    assert set(rows) == {"X", "Y"}
    assert rows["X"]["total_activity_count"] == 1


def test_create_wbs_node_root_and_child(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "wbs-admin@example.com", "password": "secret123"})

    root = client.post(
        f"/projects/{project.id}/wbs-nodes",
        json={"parent_wbs_id": None, "wbs_short_name": "ROOT", "wbs_name": "New Root"},
    )
    assert root.status_code == 201
    root_body = root.json()
    assert root_body["parent_wbs_id"] is None
    assert root_body["wbs_name"] == "New Root"

    child = client.post(
        f"/projects/{project.id}/wbs-nodes",
        json={"parent_wbs_id": root_body["wbs_id"], "wbs_short_name": "CHILD", "wbs_name": "New Child"},
    )
    assert child.status_code == 201
    assert child.json()["parent_wbs_id"] == root_body["wbs_id"]

    rows = {r["wbs_id"]: r for r in client.get(f"/projects/{project.id}/wbs-nodes").json()}
    assert rows[root_body["wbs_id"]]["depth"] == 0
    assert rows[child.json()["wbs_id"]]["depth"] == 1


def test_create_wbs_node_rejects_unknown_parent(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "wbs-admin@example.com", "password": "secret123"})

    response = client.post(
        f"/projects/{project.id}/wbs-nodes",
        json={"parent_wbs_id": "GHOST", "wbs_short_name": "X", "wbs_name": "Orphan"},
    )
    assert response.status_code == 400


def test_delete_wbs_node(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "wbs-admin@example.com", "password": "secret123"})

    created = client.post(
        f"/projects/{project.id}/wbs-nodes",
        json={"parent_wbs_id": None, "wbs_short_name": "TMP", "wbs_name": "Temp"},
    ).json()

    response = client.delete(f"/projects/{project.id}/wbs-nodes/{created['id']}")
    assert response.status_code == 204
    assert client.get(f"/projects/{project.id}/wbs-nodes").json() == []


def test_delete_wbs_node_blocked_when_it_has_children(client, db_session):
    tenant, project = _setup(db_session)
    client.post("/auth/login", json={"email": "wbs-admin@example.com", "password": "secret123"})

    root = client.post(
        f"/projects/{project.id}/wbs-nodes",
        json={"parent_wbs_id": None, "wbs_short_name": "ROOT", "wbs_name": "Root"},
    ).json()
    client.post(
        f"/projects/{project.id}/wbs-nodes",
        json={"parent_wbs_id": root["wbs_id"], "wbs_short_name": "CHILD", "wbs_name": "Child"},
    )

    response = client.delete(f"/projects/{project.id}/wbs-nodes/{root['id']}")
    assert response.status_code == 409


def test_delete_wbs_node_blocked_when_it_has_activities(client, db_session):
    tenant, project = _setup(db_session)
    _wbs(db_session, tenant, project, "R", None, "Project", 1)
    _activity(db_session, tenant, project, "A1", "R")
    db_session.commit()
    client.post("/auth/login", json={"email": "wbs-admin@example.com", "password": "secret123"})

    node_id = client.get(f"/projects/{project.id}/wbs-nodes").json()[0]["id"]
    response = client.delete(f"/projects/{project.id}/wbs-nodes/{node_id}")
    assert response.status_code == 409


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
