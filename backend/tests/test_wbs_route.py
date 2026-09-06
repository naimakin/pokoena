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
    # seq_num ordering preserved
    assert [r["wbs_id"] for r in client.get(f"/projects/{project.id}/wbs-nodes").json()] == ["R", "C", "G", "M"]


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
