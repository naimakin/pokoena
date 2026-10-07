"""Menu-based roles: what each role unlocks, that the routes enforce it (not
just the hidden menus), legacy role values, migration 0034, and changing a
member's email."""

import importlib.util
import uuid
from pathlib import Path

import pytest

from app.models.project_membership import ProjectMembership
from app.models.subcontractor_scope_assignment import SubcontractorScopeAssignment
from app.models.user import User
from app.models.user_tenant_role import (
    ROLE_CAPABILITIES,
    Capability,
    ProjectRole,
    TenantRole,
    capabilities_for,
    parse_project_roles,
)
from tests.factories import add_membership, create_project, create_project_scope, create_tenant, create_user

PASSWORD = "secret123"
C = Capability
SEE_ALL = {C.view_overview, C.view_programme, C.view_delivery, C.view_risk, C.view_reports}


# --- the matrix ------------------------------------------------------------------


def test_role_capability_matrix():
    assert ROLE_CAPABILITIES[ProjectRole.project_manager] == SEE_ALL | {
        C.edit_programme, C.import_programme, C.manage_baselines, C.export, C.edit_progress, C.edit_risk, C.edit_reports,
    }
    assert ROLE_CAPABILITIES[ProjectRole.planner] == SEE_ALL | {
        C.edit_programme, C.import_programme, C.manage_baselines, C.export, C.edit_risk, C.edit_reports,
    }
    assert ROLE_CAPABILITIES[ProjectRole.delivery_team] == SEE_ALL | {C.edit_progress, C.export, C.edit_reports}
    assert ROLE_CAPABILITIES[ProjectRole.viewer] == SEE_ALL
    assert ROLE_CAPABILITIES[ProjectRole.dashboard_viewer] == {C.view_overview, C.view_reports}
    assert ROLE_CAPABILITIES[ProjectRole.user_management] == {C.manage_users}
    for role_caps in ROLE_CAPABILITIES.values():
        assert not role_caps & {C.manage_projects, C.review_approvals}


def test_capabilities_by_tenant_role_and_union():
    assert capabilities_for(TenantRole.company_admin, []) == frozenset(Capability)
    assert capabilities_for(TenantRole.subcontractor, [ProjectRole.activity_status_updater]) == frozenset()
    both = capabilities_for(TenantRole.company_employee, [ProjectRole.dashboard_viewer, ProjectRole.user_management])
    assert both == {C.view_overview, C.view_reports, C.manage_users}


def test_legacy_role_values_are_read_not_500():
    assert parse_project_roles(["project_administrator", "all_access", "execution", "bogus"]) == [
        ProjectRole.project_manager, ProjectRole.delivery_team,
    ]
    assert parse_project_roles(["activity_status_updater"], TenantRole.company_employee) == [ProjectRole.delivery_team]
    assert parse_project_roles(["activity_status_updater"], TenantRole.subcontractor) == [
        ProjectRole.activity_status_updater
    ]


def test_migration_0034_mapping():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0034_menu_roles.py"
    spec = importlib.util.spec_from_file_location("m0034", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    emp = "company_employee"
    assert m.map_roles(emp, ["project_administrator"]) == ["project_manager"]
    assert m.map_roles(emp, ["all_access", "execution"]) == ["project_manager", "delivery_team"]
    assert m.map_roles(emp, ["activity_status_updater"]) == ["delivery_team"]
    assert m.map_roles(emp, ["user_management"]) == ["viewer", "user_management"]
    assert m.map_roles(emp, ["execution", "user_management"]) == ["delivery_team", "user_management"]
    assert m.map_roles(emp, []) == ["viewer"]
    assert m.map_roles("subcontractor", ["activity_status_updater"]) == ["activity_status_updater"]
    assert m.map_roles("subcontractor", []) == []
    assert m.map_roles("company_admin", ["anything"]) == []
    assert m.map_roles(emp, ["planner", "viewer"]) == ["planner", "viewer"]  # already new: unchanged


# --- routes enforce it ---------------------------------------------------------------


def _setup(db, roles, *, tenant_role=TenantRole.company_employee):
    tenant = create_tenant(db, name="Caps", slug=f"caps-{uuid.uuid4().hex[:6]}")
    project = create_project(db, tenant)
    email = f"u-{uuid.uuid4().hex[:6]}@example.com"
    user = create_user(db, email, PASSWORD)
    add_membership(db, user, tenant, tenant_role, project_roles=roles)
    if tenant_role == TenantRole.company_employee:
        db.add(ProjectMembership(id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, user_id=user.id))
    else:
        scope = create_project_scope(db, tenant, project)
        db.add(
            SubcontractorScopeAssignment(
                id=uuid.uuid4(), tenant_id=tenant.id, user_id=user.id, project_scope_id=scope.id,
                assigned_by_user_id=user.id,
            )
        )
    db.commit()
    return tenant, project, email


def _call(client, method, url, **kw):
    return getattr(client, method)(url, **kw).status_code


def _endpoints(p):
    return {
        "dashboard": ("get", f"/dashboard/summary?project_id={p}", {}),
        "reports": ("get", f"/projects/{p}/report-formats", {}),
        "wbs_list": ("get", f"/projects/{p}/wbs-nodes", {}),
        "my_desk": ("get", "/my-desk/inbox", {}),
        "risks": ("get", f"/projects/{p}/risks", {}),
        "export_xer": ("get", f"/projects/{p}/export/xer", {}),
        "export_evm": ("get", f"/projects/{p}/evm/export", {}),
        "import": ("post", f"/projects/{p}/schedule-imports", {"files": {"file": ("a.xer", b"x")}}),
        "wbs_create": ("post", f"/projects/{p}/wbs-nodes", {"json": {"wbs_short_name": "N", "wbs_name": "New"}}),
        "team": ("get", "/team", {}),
    }


# For each role: endpoints that must be refused (403); every other one in
# _endpoints must NOT be 403 (it may still 404/422 for lack of data).
FORBIDDEN = {
    # wbs_list stays readable: schedule data feeds the dashboards and reports.
    ProjectRole.dashboard_viewer: {"my_desk", "export_xer", "export_evm", "import", "wbs_create", "team"},
    ProjectRole.viewer: {"export_xer", "export_evm", "import", "wbs_create", "team"},
    ProjectRole.delivery_team: {"import", "wbs_create", "team"},
    ProjectRole.planner: {"team"},
    ProjectRole.project_manager: {"team"},
    ProjectRole.user_management: {"dashboard", "reports", "wbs_list", "my_desk", "risks", "export_xer", "export_evm",
                                  "import", "wbs_create"},
}


@pytest.mark.parametrize("role", list(FORBIDDEN), ids=lambda r: r.value)
def test_routes_follow_the_role(client, db_session, role):
    _tenant, project, email = _setup(db_session, [role])
    client.post("/auth/login", json={"email": email, "password": PASSWORD})

    for name, (method, url, kw) in _endpoints(project.id).items():
        status = _call(client, method, url, **kw)
        if name in FORBIDDEN[role]:
            assert status == 403, (role.value, name, status)
        else:
            assert status != 403, (role.value, name, status)


def test_subcontractor_cannot_import_export_or_edit_the_programme(client, db_session):
    _tenant, project, email = _setup(
        db_session, [ProjectRole.activity_status_updater], tenant_role=TenantRole.subcontractor
    )
    client.post("/auth/login", json={"email": email, "password": PASSWORD})

    for name in ["import", "export_xer", "export_evm", "wbs_create", "wbs_list", "dashboard", "team"]:
        method, url, kw = _endpoints(project.id)[name]
        assert _call(client, method, url, **kw) == 403, name
    assert client.get("/subcontractor-organizations").status_code == 403
    assert client.get(f"/activities?project_id={project.id}").status_code == 200


def test_me_carries_capabilities(client, db_session):
    _tenant, _project, email = _setup(db_session, [ProjectRole.dashboard_viewer])
    login = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    me = client.get("/auth/me").json()

    assert sorted(login.json()["capabilities"]) == ["view_overview", "view_reports"]
    assert sorted(me["capabilities"]) == ["view_overview", "view_reports"]


def test_employee_cannot_hold_the_subcontractor_permission(client, db_session):
    tenant, _project, _email = _setup(db_session, [ProjectRole.viewer])
    admin = create_user(db_session, "caps-admin@example.com", PASSWORD)
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    client.post("/auth/login", json={"email": "caps-admin@example.com", "password": PASSWORD})

    response = client.post(
        "/invites",
        json={"email": "x@example.com", "full_name": "X", "role": "company_employee",
              "project_roles": ["activity_status_updater"]},
    )
    assert response.status_code == 400


# --- email change -----------------------------------------------------------------------


def _admin_and_member(db):
    tenant = create_tenant(db, name="Mail", slug=f"mail-{uuid.uuid4().hex[:6]}")
    admin = create_user(db, f"admin-{uuid.uuid4().hex[:6]}@example.com", PASSWORD)
    add_membership(db, admin, tenant, TenantRole.company_admin)
    member = create_user(db, f"old-{uuid.uuid4().hex[:6]}@example.com", PASSWORD)
    row = add_membership(db, member, tenant, TenantRole.company_employee)
    return tenant, admin, member, row


def test_admin_changes_a_members_email_and_they_sign_in_with_it(client, db_session, monkeypatch):
    logged = []
    monkeypatch.setattr("app.api.routes.team.audit.log", lambda action, **kw: logged.append(action))
    _tenant, admin, member, row = _admin_and_member(db_session)
    old = member.email
    client.post("/auth/login", json={"email": admin.email, "password": PASSWORD})

    response = client.patch(f"/team/{row.id}", json={"email": "  New.Address@Example.com "})

    assert response.status_code == 200, response.text
    assert response.json()["email"] == "new.address@example.com"
    assert "user.email_changed" in logged
    client.post("/auth/logout")
    assert client.post("/auth/login", json={"email": old, "password": PASSWORD}).status_code == 401
    assert client.post("/auth/login", json={"email": "new.address@example.com", "password": PASSWORD}).status_code == 200


def test_email_change_refusals(client, db_session):
    tenant, admin, member, row = _admin_and_member(db_session)
    taken = create_user(db_session, "taken@example.com", PASSWORD)
    other = create_tenant(db_session, name="Other", slug=f"other-{uuid.uuid4().hex[:6]}")
    shared = create_user(db_session, "shared@example.com", PASSWORD)
    shared_row = add_membership(db_session, shared, tenant, TenantRole.company_employee)
    add_membership(db_session, shared, other, TenantRole.company_employee)
    mgr = create_user(db_session, "mail-mgr@example.com", PASSWORD)
    add_membership(db_session, mgr, tenant, TenantRole.company_employee, project_roles=[ProjectRole.user_management])
    assert taken

    client.post("/auth/login", json={"email": admin.email, "password": PASSWORD})
    assert client.patch(f"/team/{row.id}", json={"email": "taken@example.com"}).status_code == 409
    assert client.patch(f"/team/{shared_row.id}", json={"email": "moved@example.com"}).status_code == 409
    assert client.patch(f"/team/{row.id}", json={"email": "not-an-email"}).status_code == 422

    # A pending invite for the new address anywhere would take the account over on acceptance.
    client.post("/invites", json={"email": "invited@example.com", "full_name": "I", "role": "company_employee",
                                  "project_roles": ["viewer"]})
    assert client.patch(f"/team/{row.id}", json={"email": "invited@example.com"}).status_code == 409

    client.post("/auth/login", json={"email": "mail-mgr@example.com", "password": PASSWORD})
    assert client.patch(f"/team/{row.id}", json={"email": "fresh@example.com"}).status_code == 403

    db_session.expire_all()
    assert db_session.get(User, member.id).email == member.email
    assert db_session.get(User, shared.id).email == "shared@example.com"


def test_no_reset_link_for_an_account_another_company_uses(client, db_session):
    tenant, admin, _member, _row = _admin_and_member(db_session)
    other = create_tenant(db_session, name="Else", slug=f"else-{uuid.uuid4().hex[:6]}")
    shared = create_user(db_session, "shared-reset@example.com", PASSWORD)
    shared_row = add_membership(db_session, shared, tenant, TenantRole.company_employee)
    add_membership(db_session, shared, other, TenantRole.company_admin)
    client.post("/auth/login", json={"email": admin.email, "password": PASSWORD})

    assert client.post(f"/team/{shared_row.id}/reset-password-link").status_code == 409
