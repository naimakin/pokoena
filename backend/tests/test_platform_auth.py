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

    list_response = client.get("/platform/tenants")
    assert list_response.status_code == 200
    assert any(t["id"] == tenant_id for t in list_response.json())

    suspend_response = client.post(f"/platform/tenants/{tenant_id}/suspend")
    assert suspend_response.status_code == 200
    assert suspend_response.json()["status"] == "suspended"


def test_non_platform_admin_cannot_manage_tenants(client, db_session):
    tenant = create_tenant(db_session)
    user = create_user(db_session, "admin2@example.com", "secret123")
    add_membership(db_session, user, tenant, TenantRole.company_admin)
    client.post("/auth/login", json={"email": "admin2@example.com", "password": "secret123"})

    response = client.get("/platform/tenants")
    assert response.status_code == 401
