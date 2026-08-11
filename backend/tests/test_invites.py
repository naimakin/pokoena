import uuid
from datetime import datetime, timedelta, timezone

from app.models.project_scope import ProjectScope
from app.models.subcontractor_scope_assignment import SubcontractorScopeAssignment
from app.models.user_tenant_role import TenantRole, UserTenantRole
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
            "role": "subcontractor",
            "project_scope_ids": [str(scope.id)],
        },
    )
    assert invite_response.status_code == 201
    assert captured["to_email"] == "newsub@example.com"
    raw_token = captured["invite_url"].rsplit("/", 1)[-1]

    preview_response = client.get(f"/invites/{raw_token}")
    assert preview_response.status_code == 200
    assert preview_response.json()["email"] == "newsub@example.com"

    accept_response = client.post(
        f"/invites/{raw_token}/accept",
        json={"full_name": "New Sub", "password": "newpassword123"},
    )
    assert accept_response.status_code == 200
    body = accept_response.json()
    assert body["email"] == "newsub@example.com"
    assert body["role"] == "subcontractor"
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

    client.post("/invites", json={"email": "employee@example.com", "role": "company_employee"})
    raw_token = captured["invite_url"].rsplit("/", 1)[-1]

    first = client.post(
        f"/invites/{raw_token}/accept", json={"full_name": "Employee One", "password": "password123"}
    )
    assert first.status_code == 200

    second = client.post(
        f"/invites/{raw_token}/accept", json={"full_name": "Employee One", "password": "password123"}
    )
    assert second.status_code == 400


def test_expired_invite_is_rejected(client, db_session, monkeypatch):
    captured = _capture_invite_url(monkeypatch)
    tenant, admin = _setup_company_admin(db_session, "admin3@example.com")

    from app.services.invites import create_invite

    invite = create_invite(
        db=db_session,
        tenant_id=tenant.id,
        email="late@example.com",
        role=TenantRole.company_employee,
        invited_by_user_id=admin.id,
    )
    invite.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()
    raw_token = captured["invite_url"].rsplit("/", 1)[-1]

    response = client.post(
        f"/invites/{raw_token}/accept", json={"full_name": "Nobody", "password": "password123"}
    )
    assert response.status_code == 400


def test_invalid_invite_token_rejected(client, db_session):
    response = client.post(
        "/invites/not-a-real-token/accept", json={"full_name": "Nobody", "password": "password123"}
    )
    assert response.status_code == 400


def test_non_admin_cannot_create_invites(client, db_session):
    tenant = create_tenant(db_session)
    employee = create_user(db_session, "employee@example.com", "secret123")
    add_membership(db_session, employee, tenant, TenantRole.company_employee)
    client.post("/auth/login", json={"email": "employee@example.com", "password": "secret123"})

    response = client.post("/invites", json={"email": "x@example.com", "role": "company_employee"})
    assert response.status_code == 403
