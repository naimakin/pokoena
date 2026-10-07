import uuid

from app.models.subcontractor_scope_assignment import SubcontractorScopeAssignment
from app.models.user_tenant_role import TenantRole
from tests.factories import (
    add_membership,
    create_activity,
    create_project,
    create_project_scope,
    create_schedule_import,
    create_tenant,
    create_update_period,
    create_user,
)


def _snap(external_id, finish, **kw):
    return {
        "external_id": external_id, "p6_task_id": None, "name": external_id, "wbs_path": kw.get("wbs_path"),
        "planned_finish": finish, "early_finish": None, "actual_finish": None,
        "is_critical": kw.get("is_critical", False), "is_longest_path": False,
        "total_float_hours": None, "status": "in_progress", "percent_complete": 20,
    }


def _setup(db_session):
    tenant = create_tenant(db_session, name="Acme", slug="acme-rplan")
    project = create_project(db_session, tenant)
    scope = create_project_scope(db_session, tenant, project, name="Steel", discipline="Structural")
    admin = create_user(db_session, "rp-admin@example.com", "secret123")
    sub = create_user(db_session, "rp-sub@example.com", "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    add_membership(db_session, sub, tenant, TenantRole.subcontractor)
    db_session.add(
        SubcontractorScopeAssignment(
            id=uuid.uuid4(), tenant_id=tenant.id, user_id=sub.id,
            project_scope_id=scope.id, assigned_by_user_id=admin.id,
        )
    )
    # SELF is company self-perform (no scope); SUB1 is in the subcontractor's scope.
    create_activity(db_session, tenant, project, "SELF")
    create_activity(db_session, tenant, project, "SUB1", project_scope_id=scope.id)
    create_schedule_import(db_session, tenant, project, admin, revision_no=1, revision_label="UPD-1",
                           snapshot=[_snap("SELF", "2026-06-01"), _snap("SUB1", "2026-06-01")])
    create_schedule_import(db_session, tenant, project, admin, revision_no=2, revision_label="UPD-2",
                           snapshot=[_snap("SELF", "2026-06-20"), _snap("SUB1", "2026-06-25")])
    db_session.commit()
    return tenant, project, scope, admin, sub


def _login(client, email):
    client.post("/auth/login", json={"email": email, "password": "secret123"})


def test_company_creates_plan_for_self_perform(client, db_session):
    tenant, project, scope, admin, sub = _setup(db_session)
    _login(client, "rp-admin@example.com")
    r = client.post(f"/projects/{project.id}/recovery-plan/plans", json={"activity_external_id": "SELF"})
    assert r.status_code == 201
    assert r.json()["status"] == "draft"
    assert r.json()["project_scope_id"] is None


def test_non_slipped_activity_rejected(client, db_session):
    tenant, project, scope, admin, sub = _setup(db_session)
    create_activity(db_session, tenant, project, "CALM")
    _login(client, "rp-admin@example.com")
    r = client.post(f"/projects/{project.id}/recovery-plan/plans", json={"activity_external_id": "CALM"})
    assert r.status_code == 400


def test_subcontractor_flow_needs_open_period(client, db_session):
    tenant, project, scope, admin, sub = _setup(db_session)
    _login(client, "rp-sub@example.com")
    # no open period yet
    assert client.post(
        f"/projects/{project.id}/recovery-plan/plans", json={"activity_external_id": "SUB1"}
    ).status_code == 400

    create_update_period(db_session, tenant, project, number=2)
    r = client.post(f"/projects/{project.id}/recovery-plan/plans", json={"activity_external_id": "SUB1"})
    assert r.status_code == 201
    plan_id = r.json()["id"]

    # sub cannot touch the self-perform activity
    assert client.post(
        f"/projects/{project.id}/recovery-plan/plans", json={"activity_external_id": "SELF"}
    ).status_code == 403

    # submit with no items → 400
    assert client.post(f"/projects/{project.id}/recovery-plan/plans/{plan_id}/submit").status_code == 400
    it = client.post(
        f"/projects/{project.id}/recovery-plan/plans/{plan_id}/items",
        json={"action": "Add night shift", "owner_name": "J. Steel"},
    )
    assert it.status_code == 201
    assert client.post(f"/projects/{project.id}/recovery-plan/plans/{plan_id}/submit").status_code == 200

    # admin review
    _login(client, "rp-admin@example.com")
    rev = client.post(
        f"/projects/{project.id}/recovery-plan/plans/{plan_id}/review",
        json={"decision": "needs_revision", "note": "add dates"},
    )
    assert rev.status_code == 200
    assert rev.json()["status"] == "needs_revision" and rev.json()["revision_no"] == 2

    # reviewing a non-submitted plan → 409
    assert client.post(
        f"/projects/{project.id}/recovery-plan/plans/{plan_id}/review", json={"decision": "accept"}
    ).status_code == 409


def test_item_reorder(client, db_session):
    tenant, project, scope, admin, sub = _setup(db_session)
    _login(client, "rp-admin@example.com")
    plan_id = client.post(
        f"/projects/{project.id}/recovery-plan/plans", json={"activity_external_id": "SELF"}
    ).json()["id"]
    a = client.post(f"/projects/{project.id}/recovery-plan/plans/{plan_id}/items", json={"action": "one"}).json()
    b = client.post(f"/projects/{project.id}/recovery-plan/plans/{plan_id}/items", json={"action": "two"}).json()
    out = client.put(
        f"/projects/{project.id}/recovery-plan/plans/{plan_id}/items/order",
        json={"ordered_item_ids": [b["id"], a["id"]]},
    ).json()
    assert [i["action"] for i in out] == ["two", "one"]


def test_cross_tenant_plan_not_found(client, db_session):
    tenant, project, scope, admin, sub = _setup(db_session)
    other_tenant = create_tenant(db_session, name="Other", slug="other-rplan")
    other_project = create_project(db_session, other_tenant)
    other_admin = create_user(db_session, "other-rp@example.com", "secret123")
    add_membership(db_session, other_admin, other_tenant, TenantRole.company_admin)

    _login(client, "rp-admin@example.com")
    plan_id = client.post(
        f"/projects/{project.id}/recovery-plan/plans", json={"activity_external_id": "SELF"}
    ).json()["id"]

    _login(client, "other-rp@example.com")
    assert client.get(
        f"/projects/{other_project.id}/recovery-plan/plans/{plan_id}"
    ).status_code in (403, 404)


def test_delivery_team_acknowledges_but_not_their_own_plan(client, db_session):
    """Acknowledging a plan is no longer company-admin only: anyone who manages
    progress may — except on a plan they wrote."""
    from app.models.project_membership import ProjectMembership
    from app.models.user_tenant_role import ProjectRole

    tenant, project, scope, admin, sub = _setup(db_session)
    for email in ("rp-pm@example.com", "rp-pm2@example.com"):
        user = create_user(db_session, email, "secret123")
        add_membership(db_session, user, tenant, TenantRole.company_employee, project_roles=[ProjectRole.delivery_team])
        db_session.add(ProjectMembership(id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, user_id=user.id))
    viewer = create_user(db_session, "rp-viewer@example.com", "secret123")
    add_membership(db_session, viewer, tenant, TenantRole.company_employee, project_roles=[ProjectRole.viewer])
    db_session.add(ProjectMembership(id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, user_id=viewer.id))
    db_session.commit()
    base = f"/projects/{project.id}/recovery-plan/plans"

    _login(client, "rp-pm@example.com")
    plan_id = client.post(base, json={"activity_external_id": "SELF"}).json()["id"]
    client.post(f"{base}/{plan_id}/items", json={"action": "Second crew", "owner_name": "Site"})
    assert client.post(f"{base}/{plan_id}/submit").status_code == 200
    assert client.post(f"{base}/{plan_id}/review", json={"decision": "accept"}).status_code == 403  # own plan

    _login(client, "rp-viewer@example.com")
    assert client.post(f"{base}/{plan_id}/review", json={"decision": "accept"}).status_code == 403

    _login(client, "rp-pm2@example.com")
    ack = client.post(f"{base}/{plan_id}/review", json={"decision": "accept"})
    assert ack.status_code == 200 and ack.json()["status"] == "accepted"


def test_plan_needed_only_for_real_slips():
    from app.services.mitigation import _plan_required

    assert _plan_required({"slip_days": 5, "is_critical": False, "is_longest_path": False})
    assert _plan_required({"slip_days": 1, "is_critical": True, "is_longest_path": False})
    assert not _plan_required({"slip_days": 4, "is_critical": False, "is_longest_path": True})
    assert not _plan_required({"slip_days": 0, "is_critical": True, "is_longest_path": True})
