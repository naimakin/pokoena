"""User administration and subcontractor scopes by rule.

- Scopes name their activities by P6 WBS (with subtree) and activity code
  values; matching is OR within a code type, AND across types and with WBS; an
  activity matched by two scopes goes to the oldest (services/scope_rules.py).
- PATCH /team/{id} edits a member's details, roles, projects and scopes.
- Subcontractors hold no company roles: only "update progress" or view only.
"""

import importlib.util
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.models.activity import Activity
from app.models.activity_code import ActivityCodeType, ActivityCodeValue, TaskActivityCode
from app.models.project_membership import ProjectMembership
from app.models.project_scope import ProjectScope
from app.models.subcontractor_scope_assignment import SubcontractorScopeAssignment
from app.models.update_period import UpdatePeriod, UpdatePeriodStatus
from app.models.user_tenant_role import ProjectRole, TenantRole, UserTenantRole
from app.models.wbs_node import WbsNode
from app.services.scope_rules import apply_scope_rules
from tests.factories import add_membership, create_activity, create_project, create_tenant, create_user

PASSWORD = "secret123"


def _login(client, email):
    response = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text


def _wbs(db, tenant, project, wbs_id, parent=None):
    db.add(
        WbsNode(
            id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, wbs_id=wbs_id,
            parent_wbs_id=parent, wbs_short_name=wbs_id, wbs_name=wbs_id,
        )
    )


def _code_type(db, tenant, project, type_id):
    row = ActivityCodeType(id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, actv_code_type_id=type_id, name=type_id)
    db.add(row)
    db.flush()
    return row


def _code_value(db, tenant, project, code_type, code_id, parent=None):
    row = ActivityCodeValue(
        id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, code_type_id=code_type.id,
        actv_code_id=code_id, name=code_id, parent_actv_code_id=parent,
    )
    db.add(row)
    db.flush()
    return row


def _tag(db, tenant, project, activity, value):
    db.add(
        TaskActivityCode(
            id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id,
            activity_id=activity.id, code_value_id=value.id,
        )
    )


def _programme(db):
    """WBS: SITE > {BLD-A > {A-MEP}, BLD-B}. Codes: DISC = {MEP, CIV}, AREA = {N}.

    A1  BLD-A        MEP N
    A2  A-MEP        MEP
    A3  A-MEP        CIV
    B1  BLD-B        MEP N
    """
    tenant = create_tenant(db, name="Scopes", slug=f"scopes-{uuid.uuid4().hex[:6]}")
    project = create_project(db, tenant)
    for wbs_id, parent in [("SITE", None), ("BLD-A", "SITE"), ("A-MEP", "BLD-A"), ("BLD-B", "SITE")]:
        _wbs(db, tenant, project, wbs_id, parent)
    disc = _code_type(db, tenant, project, "DISC")
    area = _code_type(db, tenant, project, "AREA")
    mep = _code_value(db, tenant, project, disc, "MEP")
    civ = _code_value(db, tenant, project, disc, "CIV")
    north = _code_value(db, tenant, project, area, "N")
    acts = {
        "A1": create_activity(db, tenant, project, "A1", wbs_path="BLD-A", task_type="TT_Task"),
        "A2": create_activity(db, tenant, project, "A2", wbs_path="A-MEP", task_type="TT_Task"),
        "A3": create_activity(db, tenant, project, "A3", wbs_path="A-MEP", task_type="TT_Task"),
        "B1": create_activity(db, tenant, project, "B1", wbs_path="BLD-B", task_type="TT_Task"),
    }
    for key, values in {"A1": [mep, north], "A2": [mep], "A3": [civ], "B1": [mep, north]}.items():
        for value in values:
            _tag(db, tenant, project, acts[key], value)
    db.commit()
    return tenant, project, acts


def _scope(db, tenant, project, name, wbs_ids=(), code_value_ids=(), created_at=None):
    row = ProjectScope(
        id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, name=name, discipline="General",
        wbs_ids=list(wbs_ids), code_value_ids=list(code_value_ids),
    )
    if created_at:
        row.created_at = created_at
    db.add(row)
    db.commit()
    return row


def _scope_of(db, acts):
    db.expire_all()
    return {key: db.get(Activity, a.id).project_scope_id for key, a in acts.items()}


# --- rule matching ------------------------------------------------------------


def test_wbs_rule_takes_the_whole_subtree(db_session):
    tenant, project, acts = _programme(db_session)
    scope = _scope(db_session, tenant, project, "Building A", wbs_ids=["BLD-A"])

    apply_scope_rules(db_session, tenant.id, project.id)

    got = _scope_of(db_session, acts)
    assert {k for k, v in got.items() if v == scope.id} == {"A1", "A2", "A3"}


def test_codes_are_or_within_a_type_and_and_across_types_and_with_wbs(db_session):
    tenant, project, acts = _programme(db_session)
    either = _scope(db_session, tenant, project, "MEP or CIV", code_value_ids=["MEP", "CIV"])
    apply_scope_rules(db_session, tenant.id, project.id)
    assert {k for k, v in _scope_of(db_session, acts).items() if v == either.id} == {"A1", "A2", "A3", "B1"}

    either.code_value_ids = ["MEP", "N"]  # MEP AND north
    either.wbs_ids = ["BLD-A"]  # ... in building A
    db_session.commit()
    apply_scope_rules(db_session, tenant.id, project.id)
    assert {k for k, v in _scope_of(db_session, acts).items() if v == either.id} == {"A1"}


def test_an_activity_matched_twice_goes_to_the_oldest_scope_and_manual_scopes_are_kept(db_session):
    tenant, project, acts = _programme(db_session)
    now = datetime.now(timezone.utc)
    older = _scope(db_session, tenant, project, "All MEP", code_value_ids=["MEP"], created_at=now - timedelta(days=2))
    newer = _scope(db_session, tenant, project, "Building A", wbs_ids=["BLD-A"], created_at=now - timedelta(days=1))
    manual = _scope(db_session, tenant, project, "Hand-picked")
    acts["B1"].project_scope_id = manual.id
    db_session.commit()

    counts = apply_scope_rules(db_session, tenant.id, project.id)

    got = _scope_of(db_session, acts)
    assert got == {"A1": older.id, "A2": older.id, "A3": newer.id, "B1": manual.id}
    assert counts == {older.id: 2, newer.id: 1, manual.id: 1}


def test_clearing_a_rule_releases_its_activities(db_session):
    tenant, project, acts = _programme(db_session)
    scope = _scope(db_session, tenant, project, "Building B", wbs_ids=["BLD-B"])
    apply_scope_rules(db_session, tenant.id, project.id)
    assert _scope_of(db_session, acts)["B1"] == scope.id

    scope.wbs_ids = ["BLD-A"]
    db_session.commit()
    apply_scope_rules(db_session, tenant.id, project.id)

    got = _scope_of(db_session, acts)
    assert got["B1"] is None and got["A1"] == scope.id


# --- scope API -----------------------------------------------------------------


def _admin(db, tenant, email=None):
    email = email or f"admin-{uuid.uuid4().hex[:6]}@example.com"
    user = create_user(db, email, PASSWORD)
    add_membership(db, user, tenant, TenantRole.company_admin)
    return email


def test_scope_api_create_preview_update_delete(client, db_session):
    tenant, project, acts = _programme(db_session)
    _login(client, _admin(db_session, tenant))

    preview = client.post(f"/projects/{project.id}/scopes/preview", json={"wbs_ids": ["A-MEP"]})
    assert preview.status_code == 200
    assert preview.json()["count"] == 2
    assert [a["external_id"] for a in preview.json()["sample"]] == ["A2", "A3"]

    created = client.post(
        f"/projects/{project.id}/scopes",
        json={"name": "MEP sub", "discipline": "MEP", "code_value_ids": ["MEP"]},
    )
    assert created.status_code == 201, created.text
    scope_id = created.json()["id"]
    assert created.json()["activity_count"] == 3
    assert created.json()["code_value_ids"] == ["MEP"]

    # Another rule overlapping it: B1 is already held by the older scope.
    overlap = client.post(f"/projects/{project.id}/scopes/preview", json={"wbs_ids": ["BLD-B"]})
    assert overlap.json()["claimed_elsewhere"] == 1
    own = client.post(f"/projects/{project.id}/scopes/preview?scope_id={scope_id}", json={"wbs_ids": ["BLD-B"]})
    assert own.json()["claimed_elsewhere"] == 0

    updated = client.patch(f"/projects/{project.id}/scopes/{scope_id}", json={"wbs_ids": ["BLD-B"]})
    assert updated.status_code == 200
    assert updated.json()["activity_count"] == 1  # MEP AND in BLD-B

    listed = client.get(f"/projects/{project.id}/scopes").json()
    assert [(s["name"], s["activity_count"]) for s in listed] == [("MEP sub", 1)]

    assert client.delete(f"/projects/{project.id}/scopes/{scope_id}").status_code == 204
    assert client.get(f"/projects/{project.id}/scopes").json() == []
    assert all(v is None for v in _scope_of(db_session, acts).values())


def test_only_a_company_admin_manages_scopes(client, db_session):
    tenant, project, _acts = _programme(db_session)
    employee = create_user(db_session, "pm-scopes@example.com", PASSWORD)
    add_membership(db_session, employee, tenant, TenantRole.company_employee, project_roles=[ProjectRole.project_administrator])
    _login(client, "pm-scopes@example.com")

    response = client.post(f"/projects/{project.id}/scopes", json={"name": "X", "wbs_ids": ["SITE"]})

    assert response.status_code == 403


def test_subcontractor_sees_the_activities_its_rule_selects(client, db_session):
    tenant, project, _acts = _programme(db_session)
    _login(client, _admin(db_session, tenant))
    scope_id = client.post(f"/projects/{project.id}/scopes", json={"name": "Bldg B", "wbs_ids": ["BLD-B"]}).json()["id"]
    sub = create_user(db_session, "sub-rule@example.com", PASSWORD)
    add_membership(db_session, sub, tenant, TenantRole.subcontractor)
    db_session.add(
        SubcontractorScopeAssignment(
            id=uuid.uuid4(), tenant_id=tenant.id, user_id=sub.id,
            project_scope_id=uuid.UUID(scope_id), assigned_by_user_id=sub.id,
        )
    )
    db_session.commit()

    _login(client, "sub-rule@example.com")

    assert [p["id"] for p in client.get("/projects").json()] == [str(project.id)]
    assert [a["external_id"] for a in client.get(f"/activities?project_id={project.id}").json()] == ["B1"]


# --- team editing ----------------------------------------------------------------


def _member(db, tenant, email, role, project_roles=None):
    user = create_user(db, email, PASSWORD)
    membership = add_membership(db, user, tenant, role, project_roles=project_roles)
    return user, membership


def test_team_list_carries_projects_scopes_and_firm(client, db_session):
    tenant, project, _acts = _programme(db_session)
    _login(client, _admin(db_session, tenant))
    employee, emp_row = _member(db_session, tenant, "emp-list@example.com", TenantRole.company_employee, [ProjectRole.execution])
    db_session.add(ProjectMembership(id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, user_id=employee.id))
    db_session.commit()

    rows = {r["email"]: r for r in client.get("/team").json()}

    assert rows["emp-list@example.com"]["project_ids"] == [str(project.id)]
    assert rows["emp-list@example.com"]["scope_ids"] == []


def test_admin_edits_an_employees_details_roles_and_projects(client, db_session):
    tenant, project, _acts = _programme(db_session)
    other = create_project(db_session, tenant, name="Other")
    _login(client, _admin(db_session, tenant))
    employee, row = _member(db_session, tenant, "emp-edit@example.com", TenantRole.company_employee, [ProjectRole.execution])
    db_session.add(ProjectMembership(id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, user_id=employee.id))
    db_session.commit()

    response = client.patch(
        f"/team/{row.id}",
        json={
            "full_name": "Emp Renamed",
            "title": "Planner",
            "project_roles": ["project_administrator", "execution"],
            "project_ids": [str(other.id)],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["full_name"] == "Emp Renamed" and body["title"] == "Planner"
    assert body["project_roles"] == ["project_administrator", "execution"]
    assert body["project_ids"] == [str(other.id)]


def test_subcontractor_cannot_be_given_company_roles(client, db_session):
    tenant, _project, _acts = _programme(db_session)
    _login(client, _admin(db_session, tenant))
    _sub, row = _member(db_session, tenant, "sub-roles@example.com", TenantRole.subcontractor)

    for role in ["project_administrator", "all_access", "execution", "user_management"]:
        response = client.patch(f"/team/{row.id}", json={"project_roles": [role]})
        assert response.status_code == 400, role

    view_only = client.patch(f"/team/{row.id}", json={"project_roles": []})
    assert view_only.status_code == 200 and view_only.json()["project_roles"] == []


def test_subcontractor_invite_refuses_company_roles_and_allows_view_only(client, db_session):
    tenant, _project, _acts = _programme(db_session)
    _login(client, _admin(db_session, tenant))
    base = {"full_name": "Sub", "role": "subcontractor"}

    refused = client.post("/invites", json={**base, "email": "s1@example.com", "project_roles": ["project_administrator"]})
    view_only = client.post("/invites", json={**base, "email": "s2@example.com", "project_roles": []})

    assert refused.status_code == 400
    assert view_only.status_code == 201


def test_admin_assigns_a_subcontractors_scopes_and_firm(client, db_session):
    tenant, project, _acts = _programme(db_session)
    _login(client, _admin(db_session, tenant))
    scope = _scope(db_session, tenant, project, "Bldg A", wbs_ids=["BLD-A"])
    _sub, row = _member(db_session, tenant, "sub-scopes@example.com", TenantRole.subcontractor)
    org = client.post("/subcontractor-organizations", json={"name": "Volt Ltd", "discipline": "MEP"}).json()

    response = client.patch(f"/team/{row.id}", json={"scope_ids": [str(scope.id)], "subcontractor_org_id": org["id"]})

    assert response.status_code == 200, response.text
    assert response.json()["scope_ids"] == [str(scope.id)]
    assert response.json()["subcontractor_org_name"] == "Volt Ltd"

    cleared = client.patch(f"/team/{row.id}", json={"scope_ids": []})
    assert cleared.json()["scope_ids"] == []


def test_scope_and_project_fields_follow_the_member_type(client, db_session):
    tenant, project, _acts = _programme(db_session)
    _login(client, _admin(db_session, tenant))
    _emp, emp_row = _member(db_session, tenant, "emp-type@example.com", TenantRole.company_employee, [ProjectRole.execution])
    _sub, sub_row = _member(db_session, tenant, "sub-type@example.com", TenantRole.subcontractor)

    assert client.patch(f"/team/{emp_row.id}", json={"scope_ids": []}).status_code == 400
    assert client.patch(f"/team/{sub_row.id}", json={"project_ids": [str(project.id)]}).status_code == 400


def test_unknown_project_or_scope_is_refused(client, db_session):
    tenant, _project, _acts = _programme(db_session)
    other_tenant = create_tenant(db_session, name="Else", slug="else-team")
    foreign = create_project(db_session, other_tenant)
    _login(client, _admin(db_session, tenant))
    _emp, emp_row = _member(db_session, tenant, "emp-foreign@example.com", TenantRole.company_employee, [ProjectRole.execution])

    assert client.patch(f"/team/{emp_row.id}", json={"project_ids": [str(foreign.id)]}).status_code == 400


def test_user_management_employee_cannot_grant_admin_roles_or_touch_admins(client, db_session):
    tenant, _project, _acts = _programme(db_session)
    admin_email = _admin(db_session, tenant)
    admin_row = db_session.query(UserTenantRole).filter(UserTenantRole.role == TenantRole.company_admin,
                                                        UserTenantRole.tenant_id == tenant.id).one()
    _mgr, _ = _member(db_session, tenant, "mgr@example.com", TenantRole.company_employee, [ProjectRole.user_management])
    _emp, emp_row = _member(db_session, tenant, "emp-mgr@example.com", TenantRole.company_employee, [ProjectRole.execution])
    assert admin_email
    _login(client, "mgr@example.com")

    escalate = client.patch(f"/team/{emp_row.id}", json={"project_roles": ["user_management"]})
    ordinary = client.patch(f"/team/{emp_row.id}", json={"project_roles": ["execution", "activity_status_updater"]})
    edit_admin = client.patch(f"/team/{admin_row.id}", json={"title": "Boss"})
    remove_admin = client.delete(f"/team/{admin_row.id}")

    assert escalate.status_code == 403
    assert ordinary.status_code == 200
    assert edit_admin.status_code == 403
    assert remove_admin.status_code == 403


def test_nobody_changes_their_own_access(client, db_session):
    tenant, _project, _acts = _programme(db_session)
    _mgr, mgr_row = _member(db_session, tenant, "self@example.com", TenantRole.company_employee, [ProjectRole.user_management])
    _login(client, "self@example.com")

    assert client.patch(f"/team/{mgr_row.id}", json={"project_roles": ["project_administrator"]}).status_code == 400
    assert client.patch(f"/team/{mgr_row.id}", json={"title": "Lead"}).status_code == 200


def test_removed_member_can_be_restored(client, db_session):
    tenant, _project, _acts = _programme(db_session)
    _login(client, _admin(db_session, tenant))
    _emp, row = _member(db_session, tenant, "back@example.com", TenantRole.company_employee, [ProjectRole.execution])
    assert client.delete(f"/team/{row.id}").status_code == 204

    response = client.patch(f"/team/{row.id}", json={"is_active": True})

    assert response.status_code == 200 and response.json()["is_active"] is True


def test_subcontractor_with_user_management_left_over_cannot_open_the_team(client, db_session):
    tenant, _project, _acts = _programme(db_session)
    _member(db_session, tenant, "sub-um@example.com", TenantRole.subcontractor, [ProjectRole.user_management])
    _login(client, "sub-um@example.com")

    assert client.get("/team").status_code == 403


def test_view_only_subcontractor_cannot_update_progress(client, db_session):
    tenant, project, acts = _programme(db_session)
    scope = _scope(db_session, tenant, project, "Bldg B", wbs_ids=["BLD-B"])
    apply_scope_rules(db_session, tenant.id, project.id)
    sub, _row = _member(db_session, tenant, "sub-view@example.com", TenantRole.subcontractor, [])
    db_session.add_all([
        SubcontractorScopeAssignment(
            id=uuid.uuid4(), tenant_id=tenant.id, user_id=sub.id, project_scope_id=scope.id, assigned_by_user_id=sub.id,
        ),
        UpdatePeriod(
            id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, period_number=1, label="P1",
            opens_at=datetime.now(timezone.utc) - timedelta(days=1),
            deadline_at=datetime.now(timezone.utc) + timedelta(days=7), status=UpdatePeriodStatus.open,
        ),
    ])
    db_session.commit()
    _login(client, "sub-view@example.com")

    assert client.get(f"/activities?project_id={project.id}").status_code == 200
    assert client.patch(f"/activities/{acts['B1'].id}", json={"percent_complete": 40}).status_code == 403


# --- migration 0033 -----------------------------------------------------------------


def test_migration_maps_subcontractor_roles_to_update_or_view_only():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0033_scope_rules.py"
    spec = importlib.util.spec_from_file_location("m0033", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.subcontractor_roles(["execution", "user_management"]) == ["activity_status_updater"]
    assert module.subcontractor_roles(["project_administrator"]) == ["activity_status_updater"]
    assert module.subcontractor_roles(["user_management"]) == []
    assert module.subcontractor_roles([]) == []


def test_project_administrator_alone_does_not_open_the_team(client, db_session):
    tenant, _project, _acts = _programme(db_session)
    _member(db_session, tenant, "pa@example.com", TenantRole.company_employee, [ProjectRole.project_administrator])
    _login(client, "pa@example.com")

    assert client.get("/team").status_code == 403


# --- update periods -------------------------------------------------------------


def test_admin_opens_one_update_period_at_a_time(client, db_session):
    tenant, project, _acts = _programme(db_session)
    _login(client, _admin(db_session, tenant))
    deadline = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()

    first = client.post("/update-periods", json={"project_id": str(project.id), "deadline_at": deadline})
    again = client.post("/update-periods", json={"project_id": str(project.id), "deadline_at": deadline})

    assert first.status_code == 201, first.text
    assert first.json()["period_number"] == 1 and first.json()["label"] == "Update 1"
    assert again.status_code == 409

    client.post(f"/update-periods/{first.json()['id']}/close")
    second = client.post(
        "/update-periods", json={"project_id": str(project.id), "deadline_at": deadline, "label": "October update"}
    )
    assert second.json()["period_number"] == 2 and second.json()["label"] == "October update"


def test_update_period_deadline_must_be_ahead(client, db_session):
    tenant, project, _acts = _programme(db_session)
    _login(client, _admin(db_session, tenant))
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

    assert client.post("/update-periods", json={"project_id": str(project.id), "deadline_at": past}).status_code == 400
