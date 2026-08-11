from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_tenant, create_user


def _setup_company_admin(db_session, email="admin@example.com", password="secret123"):
    tenant = create_tenant(db_session)
    user = create_user(db_session, email, password)
    add_membership(db_session, user, tenant, TenantRole.company_admin)
    return tenant, user


def test_login_success_sets_cookie(client, db_session):
    _setup_company_admin(db_session, "admin@example.com", "secret123")

    response = client.post("/auth/login", json={"email": "admin@example.com", "password": "secret123"})

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "admin@example.com"
    assert body["role"] == "company_admin"
    assert "poko_tenant_session" in response.cookies
    assert "poko_tenant_refresh" in response.cookies


def test_login_invalid_password_rejected(client, db_session):
    _setup_company_admin(db_session, "admin2@example.com", "secret123")

    response = client.post("/auth/login", json={"email": "admin2@example.com", "password": "wrong"})

    assert response.status_code == 401


def test_login_user_with_no_tenant_access_rejected(client, db_session):
    create_user(db_session, "orphan@example.com", "secret123")

    response = client.post("/auth/login", json={"email": "orphan@example.com", "password": "secret123"})

    assert response.status_code == 401


def test_me_requires_authentication(client):
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_returns_current_user_after_login(client, db_session):
    _setup_company_admin(db_session, "admin3@example.com", "secret123")
    client.post("/auth/login", json={"email": "admin3@example.com", "password": "secret123"})

    response = client.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == "admin3@example.com"


def test_logout_clears_session(client, db_session):
    _setup_company_admin(db_session, "admin4@example.com", "secret123")
    client.post("/auth/login", json={"email": "admin4@example.com", "password": "secret123"})

    logout_response = client.post("/auth/logout")
    assert logout_response.status_code == 200

    me_response = client.get("/auth/me")
    assert me_response.status_code == 401


def test_refresh_rotates_session(client, db_session):
    _setup_company_admin(db_session, "admin5@example.com", "secret123")
    client.post("/auth/login", json={"email": "admin5@example.com", "password": "secret123"})

    response = client.post("/auth/refresh")

    assert response.status_code == 200
    assert response.json()["email"] == "admin5@example.com"


def test_login_rate_limited_after_repeated_attempts(client, db_session):
    _setup_company_admin(db_session, "admin6@example.com", "secret123")

    for _ in range(10):
        client.post("/auth/login", json={"email": "admin6@example.com", "password": "wrong"})

    response = client.post("/auth/login", json={"email": "admin6@example.com", "password": "wrong"})
    assert response.status_code == 429
