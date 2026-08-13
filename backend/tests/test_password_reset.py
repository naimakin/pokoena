from app.core.security import verify_password
from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_tenant, create_user


def _setup_platform_admin(db_session, email="staff@pokoena.com") -> None:
    create_user(db_session, email, "secret123", is_platform_admin=True)


def test_reset_link_requires_accepted_admin(client, db_session):
    _setup_platform_admin(db_session)
    client.post("/platform-auth/login", json={"email": "staff@pokoena.com", "password": "secret123"})

    create_response = client.post(
        "/platform/tenants",
        json={
            "name": "Pending Co",
            "slug": "pending-co",
            "admin_email": "founder@pendingco.com",
            "admin_full_name": "Founder",
        },
    )
    tenant_id = create_response.json()["id"]

    # The invite was never accepted — no account exists yet to reset.
    response = client.post(f"/platform/tenants/{tenant_id}/admin-reset-link")
    assert response.status_code == 404


def test_platform_admin_can_generate_and_use_a_reset_link_for_a_tenant_admin(client, db_session):
    _setup_platform_admin(db_session)
    tenant = create_tenant(db_session, name="Acme Co")
    admin_user = create_user(db_session, "admin@acme.com", "original-password")
    add_membership(db_session, admin_user, tenant, TenantRole.company_admin)

    client.post("/platform-auth/login", json={"email": "staff@pokoena.com", "password": "secret123"})
    link_response = client.post(f"/platform/tenants/{tenant.id}/admin-reset-link")
    assert link_response.status_code == 200
    body = link_response.json()
    assert body["email"] == "admin@acme.com"
    assert "/reset-password/" in body["reset_url"]
    raw_token = body["reset_url"].rsplit("/", 1)[-1]

    preview_response = client.get(f"/reset-password/{raw_token}")
    assert preview_response.status_code == 200
    assert preview_response.json() == {"email": "admin@acme.com", "is_platform_admin": False}

    submit_response = client.post(f"/reset-password/{raw_token}", json={"password": "brand-new-password"})
    assert submit_response.status_code == 200

    db_session.refresh(admin_user)
    assert verify_password("brand-new-password", admin_user.hashed_password)
    assert not verify_password("original-password", admin_user.hashed_password)

    # Single-use: the same link can't be replayed.
    replay_response = client.post(f"/reset-password/{raw_token}", json={"password": "another-one"})
    assert replay_response.status_code == 400

    # The new password actually works for a real login.
    login_response = client.post("/auth/login", json={"email": "admin@acme.com", "password": "brand-new-password"})
    assert login_response.status_code == 200


def test_invalid_reset_token_rejected(client, db_session):
    response = client.get("/reset-password/not-a-real-token")
    assert response.status_code == 400

    response = client.post("/reset-password/not-a-real-token", json={"password": "whatever123"})
    assert response.status_code == 400


def test_non_platform_admin_cannot_generate_reset_links(client, db_session):
    tenant = create_tenant(db_session)
    user = create_user(db_session, "notstaff@example.com", "secret123")
    add_membership(db_session, user, tenant, TenantRole.company_admin)
    client.post("/auth/login", json={"email": "notstaff@example.com", "password": "secret123"})

    response = client.post(f"/platform/tenants/{tenant.id}/admin-reset-link")
    assert response.status_code == 401
