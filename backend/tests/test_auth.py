import uuid

from app.core.security import hash_password
from app.models.user import User, UserRole


def _create_user(db_session, email: str, password: str, role: UserRole = UserRole.admin) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=hash_password(password),
        full_name="Test User",
        role=role,
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_login_success_sets_cookie(client, db_session):
    _create_user(db_session, "admin@example.com", "secret123")

    response = client.post("/auth/login", json={"email": "admin@example.com", "password": "secret123"})

    assert response.status_code == 200
    assert response.json()["email"] == "admin@example.com"
    assert "poko_session" in response.cookies


def test_login_invalid_password_rejected(client, db_session):
    _create_user(db_session, "admin2@example.com", "secret123")

    response = client.post("/auth/login", json={"email": "admin2@example.com", "password": "wrong"})

    assert response.status_code == 401


def test_me_requires_authentication(client):
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_returns_current_user_after_login(client, db_session):
    _create_user(db_session, "admin3@example.com", "secret123")
    client.post("/auth/login", json={"email": "admin3@example.com", "password": "secret123"})

    response = client.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == "admin3@example.com"
