import uuid
from datetime import datetime, timedelta, timezone

from app.models.project_scope import ProjectScope
from app.models.subcontractor_scope_assignment import SubcontractorScopeAssignment
from app.models.user_tenant_role import ProjectRole, TenantRole, UserTenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user


def _capture_invite_url(monkeypatch) -> dict:
    captured: dict = {}

    def fake_send_invite_email(to_email, invite_url, role, tenant_name):
        captured["to_email"] = to_email
        captured["invite_url"] = invite_url
        captured["role"] = role

    monkeypatch.setattr("app.worker.tasks._send_invite_email", fake_send_invite_email)
    return captured


def _setup_company_admin(db_session, email="admin@example.com"):
    tenant = create_tenant(db_session)
    admin = create_user(db_session, email, "secret123")
    add_membership(db_session, admin, tenant, TenantRole.company_admin)
    return tenant, admin


def test_company_admin_can_invite_subcontractor_and_they_can_accept(client, db_session, monkeypatch):
    captured = _capture_invite_url(monkeypatch)
    tenant, _admin = _setup_company_admin(db_session, "admin@example.com")
    project = create_project(db_session, tenant)
    scope = ProjectScope(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        project_id=project.id,
        name="MEP",
        discipline="MEP",
    )
    db_session.add(scope)
    db_session.commit()

    client.post("/auth/login", json={"email": "admin@example.com", "password": "secret123"})

    invite_response = client.post(
        "/invites",
        json={
            "email": "newsub@example.com",
            "full_name": "New Sub",
            "role": "subcontractor",
            "project_roles": ["activity_status_updater"],
            "project_scope_ids": [str(scope.id)],
        },
    )
    assert invite_response.status_code == 201
    assert captured["to_email"] == "newsub@example.com"
    # The response itself carries the invite link (no email provider is wired
    # up in this deployment — see services/invites.create_invite) — and it's
    # the same token that would have been emailed.
    assert invite_response.json()["invite_url"] == captured["invite_url"]
    raw_token = captured["invite_url"].rsplit("/", 1)[-1]

    preview_response = client.get(f"/invites/{raw_token}")
    assert preview_response.status_code == 200
    assert preview_response.json()["email"] == "newsub@example.com"
    assert preview_response.json()["full_name"] == "New Sub"

    accept_response = client.post(
        f"/invites/{raw_token}/accept",
        json={"password": "newpassword123"},
    )
    assert accept_response.status_code == 200
    body = accept_response.json()
    assert body["email"] == "newsub@example.com"
    assert body["full_name"] == "New Sub"
    assert body["role"] == "subcontractor"
    assert body["project_roles"] == ["activity_status_updater"]
    assert str(scope.id) in body["scope_ids"] or [str(s) for s in body["scope_ids"]] == [str(scope.id)]

    membership = (
        db_session.query(UserTenantRole)
        .filter(UserTenantRole.tenant_id == tenant.id, UserTenantRole.role == TenantRole.subcontractor)
        .first()
    )
    assert membership is not None
    assignment = (
        db_session.query(SubcontractorScopeAssignment)
        .filter(SubcontractorScopeAssignment.project_scope_id == scope.id)
        .first()
    )
    assert assignment is not None
    assert assignment.user_id == membership.user_id


def test_invite_cannot_be_accepted_twice(client, db_session, monkeypatch):
    captured = _capture_invite_url(monkeypatch)
    _tenant, _admin = _setup_company_admin(db_session, "admin2@example.com")
    client.post("/auth/login", json={"email": "admin2@example.com", "password": "secret123"})

    client.post(
        "/invites",
        json={
            "email": "employee@example.com",
            "full_name": "Employee One",
            "role": "company_employee",
            "project_roles": ["delivery_team"],
        },
    )
    raw_token = captured["invite_url"].rsplit("/", 1)[-1]

    first = client.post(f"/invites/{raw_token}/accept", json={"password": "password123"})
    assert first.status_code == 200

    second = client.post(f"/invites/{raw_token}/accept", json={"password": "password123"})
    assert second.status_code == 400


def test_expired_invite_is_rejected(client, db_session, monkeypatch):
    captured = _capture_invite_url(monkeypatch)
    tenant, admin = _setup_company_admin(db_session, "admin3@example.com")

    from app.services.invites import create_invite

    invite, _invite_url = create_invite(
        db=db_session,
        tenant_id=tenant.id,
        email="late@example.com",
        full_name="Nobody",
        role=TenantRole.company_employee,
        project_roles=[ProjectRole.delivery_team],
        invited_by_user_id=admin.id,
    )
    invite.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()
    raw_token = captured["invite_url"].rsplit("/", 1)[-1]

    response = client.post(f"/invites/{raw_token}/accept", json={"password": "password123"})
    assert response.status_code == 400


def test_invalid_invite_token_rejected(client, db_session):
    response = client.post(
        "/invites/not-a-real-token/accept", json={"password": "password123"}
    )
    assert response.status_code == 400


def test_non_admin_cannot_create_invites(client, db_session):
    tenant = create_tenant(db_session)
    employee = create_user(db_session, "employee@example.com", "secret123")
    add_membership(db_session, employee, tenant, TenantRole.company_employee)
    client.post("/auth/login", json={"email": "employee@example.com", "password": "secret123"})

    response = client.post(
        "/invites",
        json={"email": "x@example.com", "full_name": "X", "role": "company_employee"},
    )
    assert response.status_code == 403


def test_invite_requires_project_roles_for_employee(client, db_session, monkeypatch):
    _capture_invite_url(monkeypatch)
    _tenant, _admin = _setup_company_admin(db_session, "admin4@example.com")
    client.post("/auth/login", json={"email": "admin4@example.com", "password": "secret123"})

    response = client.post(
        "/invites",
        json={"email": "noRole@example.com", "full_name": "No Role", "role": "company_employee"},
    )
    assert response.status_code == 400


def test_user_management_project_role_can_manage_team(client, db_session, monkeypatch):
    """A company_employee holding the 'user_management' project_role can invite
    and list team members even though they're not a company_admin."""
    captured = _capture_invite_url(monkeypatch)
    tenant, _admin = _setup_company_admin(db_session, "admin5@example.com")
    manager = create_user(db_session, "manager@example.com", "secret123")
    add_membership(
        db_session, manager, tenant, TenantRole.company_employee, project_roles=[ProjectRole.user_management]
    )
    client.post("/auth/login", json={"email": "manager@example.com", "password": "secret123"})

    response = client.post(
        "/invites",
        json={
            "email": "newhire@example.com",
            "full_name": "New Hire",
            "role": "company_employee",
            "project_roles": ["delivery_team"],
        },
    )
    assert response.status_code == 201
    assert captured["to_email"] == "newhire@example.com"


def test_cannot_invite_an_email_that_already_has_an_account(client, db_session, monkeypatch):
    """Regression test: accept_invite resets whatever user matches the
    invite's email to a password the accepter chooses, with no proof they
    ever controlled that account. Without this rejection, any company_admin
    could take over an existing account — including a platform admin's — just
    by knowing its email and inviting it into their own tenant, then using
    the invite link (which the UI hands straight back to them) themselves."""
    _capture_invite_url(monkeypatch)
    tenant, _admin = _setup_company_admin(db_session, "admin6@example.com")
    victim = create_user(db_session, "victim@example.com", "victims-real-password")
    other_tenant = create_tenant(db_session, name="Other Co")
    add_membership(db_session, victim, other_tenant, TenantRole.company_admin)

    client.post("/auth/login", json={"email": "admin6@example.com", "password": "secret123"})
    response = client.post(
        "/invites",
        json={
            "email": "victim@example.com",
            "full_name": "Victim",
            "role": "company_employee",
            "project_roles": ["delivery_team"],
        },
    )
    assert response.status_code == 400

    db_session.refresh(victim)
    from app.core.security import verify_password

    assert verify_password("victims-real-password", victim.hashed_password)
