"""Integration tests for the authentication API: register, login, refresh, /me, RBAC."""
from app.authentication.password_handler import hash_password
from app.models.user import Role, User


def _register_payload(**overrides):
    payload = {
        "username": "jdoe",
        "email": "jdoe@example.com",
        "full_name": "Jane Doe",
        "password": "Sup3rSecret!",
    }
    payload.update(overrides)
    return payload


def test_register_creates_user_with_default_viewer_role(client):
    response = client.post("/api/v1/auth/register", json=_register_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "jdoe"
    assert body["email"] == "jdoe@example.com"
    assert body["is_active"] is True
    assert any(role["name"] == "viewer" for role in body["roles"])


def test_register_rejects_duplicate_username(client):
    client.post("/api/v1/auth/register", json=_register_payload())
    response = client.post(
        "/api/v1/auth/register", json=_register_payload(email="other@example.com")
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "USER_EXISTS"


def test_register_rejects_weak_password(client):
    response = client.post(
        "/api/v1/auth/register", json=_register_payload(password="weakpass")
    )
    assert response.status_code == 422


def test_login_succeeds_with_valid_credentials(client):
    client.post("/api/v1/auth/register", json=_register_payload())
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "jdoe", "password": "Sup3rSecret!"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


def test_login_fails_with_invalid_password(client):
    client.post("/api/v1/auth/register", json=_register_payload())
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "jdoe", "password": "WrongPassword!"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_me_requires_authentication(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_returns_current_user_with_valid_token(client):
    client.post("/api/v1/auth/register", json=_register_payload())
    login_response = client.post(
        "/api/v1/auth/login",
        data={"username": "jdoe", "password": "Sup3rSecret!"},
    )
    access_token = login_response.json()["access_token"]

    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert response.json()["username"] == "jdoe"


def test_refresh_issues_new_token_pair(client):
    client.post("/api/v1/auth/register", json=_register_payload())
    login_response = client.post(
        "/api/v1/auth/login",
        data={"username": "jdoe", "password": "Sup3rSecret!"},
    )
    refresh_token = login_response.json()["refresh_token"]

    response = client.post(
        "/api/v1/auth/refresh", params={"refresh_token": refresh_token}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_users_list_forbidden_for_non_admin(client):
    client.post("/api/v1/auth/register", json=_register_payload())
    login_response = client.post(
        "/api/v1/auth/login",
        data={"username": "jdoe", "password": "Sup3rSecret!"},
    )
    access_token = login_response.json()["access_token"]

    response = client.get(
        "/api/v1/users", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_ROLE"


def test_users_list_allowed_for_admin_role(client, db_session):
    client.post("/api/v1/auth/register", json=_register_payload())

    # The "admin" role is seeded once per test session (see conftest.py),
    # mirroring the real seed-roles Alembic migration - fetch it rather than
    # creating a duplicate.
    admin_role = db_session.query(Role).filter(Role.name == "admin").one()

    user = db_session.query(User).filter(User.username == "jdoe").one()
    user.roles.append(admin_role)
    db_session.commit()

    response = client.post(
        "/api/v1/auth/login",
        data={"username": "jdoe", "password": "Sup3rSecret!"},
    )
    access_token = response.json()["access_token"]

    list_response = client.get(
        "/api/v1/users", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert list_response.status_code == 200
    body = list_response.json()
    assert body["meta"]["total"] >= 1
