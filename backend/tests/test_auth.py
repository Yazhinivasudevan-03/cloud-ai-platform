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


def test_register_is_rate_limited(client):
    # RATE_LIMIT_REGISTER defaults to "10/hour" - the 11th distinct
    # registration from the same client within the window must be rejected,
    # guarding against automated mass account creation the same way login
    # is guarded against brute-force credential guessing.
    for i in range(10):
        response = client.post(
            "/api/v1/auth/register",
            json=_register_payload(username=f"user{i}", email=f"user{i}@example.com"),
        )
        assert response.status_code == 201

    response = client.post(
        "/api/v1/auth/register",
        json=_register_payload(username="user10", email="user10@example.com"),
    )
    assert response.status_code == 429


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


def test_login_failure_records_an_audit_log_row_with_a_resolvable_user_id(client, db_session):
    """Phase 23's Security evaluator counts failed logins per user_id -
    the generic AuditLogMiddleware row has none (no authenticated "current
    user" exists for a request that hasn't logged in yet), so
    AuthService.authenticate() must write its own, more precise row for
    any username that actually resolved to a real account."""
    from app.models.audit_log import AuditLog

    client.post("/api/v1/auth/register", json=_register_payload())
    registered_user_id = db_session.query(User).filter(User.username == "jdoe").one().id

    client.post("/api/v1/auth/login", data={"username": "jdoe", "password": "WrongPassword!"})

    matching = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.action == "POST /api/v1/auth/login",
            AuditLog.details == "status=401",
            AuditLog.user_id == registered_user_id,
        )
        .all()
    )
    assert len(matching) >= 1


def test_login_failure_for_unknown_username_does_not_error(client):
    """No account to resolve a user_id from - must still return a normal
    401, not raise trying to log an audit row for a nonexistent user."""
    response = client.post(
        "/api/v1/auth/login", data={"username": "totally-unknown-user", "password": "whatever"}
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


def _login(client, username: str, password: str) -> str:
    return client.post(
        "/api/v1/auth/login", data={"username": username, "password": password}
    ).json()["access_token"]


def test_update_me_sets_phone_number_and_full_name(client):
    client.post("/api/v1/auth/register", json=_register_payload(username="phoneuser", email="phoneuser@example.com"))
    token = _login(client, "phoneuser", "Sup3rSecret!")

    response = client.patch(
        "/api/v1/auth/me",
        json={"phone_number": "+14155552671", "full_name": "New Name"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["phone_number"] == "+14155552671"
    assert body["full_name"] == "New Name"

    me_response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.json()["phone_number"] == "+14155552671"


def test_update_me_rejects_non_e164_phone_number(client):
    client.post("/api/v1/auth/register", json=_register_payload(username="badphone", email="badphone@example.com"))
    token = _login(client, "badphone", "Sup3rSecret!")

    response = client.patch(
        "/api/v1/auth/me",
        json={"phone_number": "not-a-phone-number"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_update_me_requires_authentication(client):
    response = client.patch("/api/v1/auth/me", json={"phone_number": "+14155552671"})
    assert response.status_code == 401


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
