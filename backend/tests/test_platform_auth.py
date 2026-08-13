from fastapi.testclient import TestClient

from app.main import app
from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_tenant, create_user


def test_platform_login_success(client, db_session):
    create_user(db_session, "staff@pokoena.com", "secret123", is_platform_admin=True)

    response = client.post("/platform-auth/login", json={"email": "staff@pokoena.com", "password": "secret123"})

    assert response.status_code == 200
    assert response.json()["email"] == "staff@pokoena.com"
    assert "poko_platform_session" in response.cookies
    assert "poko_tenant_session" not in response.cookies


def test_platform_login_rejects_non_platform_admin(client, db_session):
    # A regular tenant user, correct password, but never granted platform admin.
    create_user(db_session, "tenant-user@example.com", "secret123", is_platform_admin=False)

    response = client.post(
        "/platform-auth/login", json={"email": "tenant-user@example.com", "password": "secret123"}
    )

    assert response.status_code == 401


def test_tenant_token_rejected_on_platform_routes(client, db_session):
    """A valid, unexpired tenant access token must never authenticate a
    platform-admin route — token_type is checked explicitly, not just presence
    of a cookie."""
    tenant = create_tenant(db_session)
    user = create_user(db_session, "admin@example.com", "secret123")
    add_membership(db_session, user, tenant, TenantRole.company_admin)
    client.post("/auth/login", json={"email": "admin@example.com", "password": "secret123"})

    response = client.get("/platform-auth/me")

    assert response.status_code == 401


def test_platform_token_rejected_on_tenant_routes(client, db_session):
    """The reverse: a valid platform access token must never authenticate a
    tenant-scoped route."""
    create_user(db_session, "staff@pokoena.com", "secret123", is_platform_admin=True)
    client.post("/platform-auth/login", json={"email": "staff@pokoena.com", "password": "secret123"})

    response = client.get("/auth/me")

    assert response.status_code == 401


def test_tenant_access_token_explicitly_rejected_even_on_platform_cookie(client, db_session):
    """Direct proof of "validate token type explicitly": a tenant_access token,
    presented under the *platform* cookie name so cookie-name separation can't
    be what's saving us, must still be rejected on the token_type check alone.
    """
    from app.core.security import create_tenant_access_token
    from app.deps import PLATFORM_SESSION_COOKIE

    tenant = create_tenant(db_session)
    user = create_user(db_session, "admin7@example.com", "secret123")
    add_membership(db_session, user, tenant, TenantRole.company_admin)

    tenant_token = create_tenant_access_token(
        user_id=user.id, tenant_id=tenant.id, role=TenantRole.company_admin.value
    )
    client.cookies.set(PLATFORM_SESSION_COOKIE, tenant_token)

    response = client.get("/platform-auth/me")

    assert response.status_code == 401


def test_platform_access_token_explicitly_rejected_even_on_tenant_cookie(client, db_session):
    from app.core.security import create_platform_access_token
    from app.deps import TENANT_SESSION_COOKIE

    user = create_user(db_session, "staff3@pokoena.com", "secret123", is_platform_admin=True)
    platform_token = create_platform_access_token(user_id=user.id)
    client.cookies.set(TENANT_SESSION_COOKIE, platform_token)

    response = client.get("/auth/me")

    assert response.status_code == 401


def test_platform_admin_can_manage_tenants(client, db_session):
    create_user(db_session, "staff2@pokoena.com", "secret123", is_platform_admin=True)
    client.post("/platform-auth/login", json={"email": "staff2@pokoena.com", "password": "secret123"})

    create_response = client.post(
        "/platform/tenants",
        json={
            "name": "New Co",
            "slug": "new-co",
            "admin_email": "founder@newco.com",
            "admin_full_name": "Founder Person",
        },
    )
    assert create_response.status_code == 201
    tenant_id = create_response.json()["id"]
    invite_url = create_response.json()["admin_invite_url"]
    assert "/invite/" in invite_url and len(invite_url.rsplit("/", 1)[-1]) > 10

    list_response = client.get("/platform/tenants")
    assert list_response.status_code == 200
    assert any(t["id"] == tenant_id for t in list_response.json())

    suspend_response = client.post(f"/platform/tenants/{tenant_id}/suspend")
    assert suspend_response.status_code == 200
    assert suspend_response.json()["status"] == "suspended"

    already_active = client.post(f"/platform/tenants/{tenant_id}/activate")
    assert already_active.status_code == 200
    assert already_active.json()["status"] == "active"

    redundant_activate = client.post(f"/platform/tenants/{tenant_id}/activate")
    assert redundant_activate.status_code == 400

    delete_response = client.delete(f"/platform/tenants/{tenant_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "deleted"

    restore_response = client.post(f"/platform/tenants/{tenant_id}/activate")
    assert restore_response.status_code == 200
    assert restore_response.json()["status"] == "active"


def test_cannot_onboard_tenant_with_admin_email_that_already_has_an_account(client, db_session):
    """Same account-takeover concern as test_invites.py's version of this,
    for the tenant-onboarding path: onboarding must not be able to hijack an
    existing account (e.g. another platform admin's) via its admin_email."""
    create_user(db_session, "staff4@pokoena.com", "secret123", is_platform_admin=True)
    client.post("/platform-auth/login", json={"email": "staff4@pokoena.com", "password": "secret123"})

    response = client.post(
        "/platform/tenants",
        json={
            "name": "Hijack Co",
            "slug": "hijack-co",
            "admin_email": "staff4@pokoena.com",
            "admin_full_name": "Not Actually Staff",
        },
    )
    assert response.status_code == 409
    # No orphaned tenant left behind by the rejected onboarding attempt.
    assert not any(t["slug"] == "hijack-co" for t in client.get("/platform/tenants").json())


def test_non_platform_admin_cannot_manage_tenants(client, db_session):
    tenant = create_tenant(db_session)
    user = create_user(db_session, "admin2@example.com", "secret123")
    add_membership(db_session, user, tenant, TenantRole.company_admin)
    client.post("/auth/login", json={"email": "admin2@example.com", "password": "secret123"})

    response = client.get("/platform/tenants")
    assert response.status_code == 401


def test_platform_admin_can_create_and_deactivate_another_admin(client, db_session):
    create_user(db_session, "founder@pokoena.com", "secret123", is_platform_admin=True)
    client.post("/platform-auth/login", json={"email": "founder@pokoena.com", "password": "secret123"})

    create_response = client.post(
        "/platform/admins",
        json={
            "email": "second@pokoena.com",
            "password": "secret456",
            "full_name": "Second Admin",
            "title": "Ops",
            "phone": "+1 555-0000",
        },
    )
    assert create_response.status_code == 201
    new_admin_id = create_response.json()["id"]

    # The new admin can log in on their own — via a second TestClient (same
    # app, same dependency overrides as `client`) so its session cookie
    # doesn't clobber the founder's session held by `client`.
    with TestClient(app) as second_client:
        other_client_login = second_client.post(
            "/platform-auth/login", json={"email": "second@pokoena.com", "password": "secret456"}
        )
        assert other_client_login.status_code == 200

    list_response = client.get("/platform/admins")
    assert list_response.status_code == 200
    assert any(a["id"] == new_admin_id for a in list_response.json())

    deactivate_response = client.post(f"/platform/admins/{new_admin_id}/deactivate")
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["is_active"] is False

    relogin = client.post(
        "/platform-auth/login", json={"email": "second@pokoena.com", "password": "secret456"}
    )
    assert relogin.status_code == 401

    already_active = client.post(f"/platform/admins/{new_admin_id}/activate")
    assert already_active.status_code == 200
    assert already_active.json()["is_active"] is True

    redundant_activate = client.post(f"/platform/admins/{new_admin_id}/activate")
    assert redundant_activate.status_code == 400

    restored_login = client.post(
        "/platform-auth/login", json={"email": "second@pokoena.com", "password": "secret456"}
    )
    assert restored_login.status_code == 200


def test_platform_admin_cannot_deactivate_self(client, db_session):
    admin = create_user(db_session, "solo@pokoena.com", "secret123", is_platform_admin=True)
    client.post("/platform-auth/login", json={"email": "solo@pokoena.com", "password": "secret123"})

    response = client.post(f"/platform/admins/{admin.id}/deactivate")
    assert response.status_code == 400


def test_non_platform_admin_cannot_create_platform_admins(client, db_session):
    tenant = create_tenant(db_session)
    user = create_user(db_session, "admin3@example.com", "secret123")
    add_membership(db_session, user, tenant, TenantRole.company_admin)
    client.post("/auth/login", json={"email": "admin3@example.com", "password": "secret123"})

    response = client.post(
        "/platform/admins",
        json={"email": "sneaky@pokoena.com", "password": "secret123", "full_name": "Sneaky"},
    )
    assert response.status_code == 401
