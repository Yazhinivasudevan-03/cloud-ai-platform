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


def _verify_email(client, register_response):
    """Completes the real (Phase 24) email-verification flow for a just-
    registered user, using the token the register response returns -
    login is gated on email_verified, so any test that logs in after
    registering needs this first."""
    token = register_response.json()["verification_token"]
    verify_response = client.get("/api/v1/auth/verify-email", params={"token": token})
    assert verify_response.status_code == 200, verify_response.text


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
    _verify_email(client, client.post("/api/v1/auth/register", json=_register_payload()))
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
    _verify_email(client, client.post("/api/v1/auth/register", json=_register_payload()))
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
    _verify_email(
        client,
        client.post(
            "/api/v1/auth/register",
            json=_register_payload(username="phoneuser", email="phoneuser@example.com"),
        ),
    )
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


def test_update_me_sets_first_last_company_and_country(client):
    _verify_email(
        client,
        client.post(
            "/api/v1/auth/register",
            json=_register_payload(username="profileuser", email="profileuser@example.com"),
        ),
    )
    token = _login(client, "profileuser", "Sup3rSecret!")

    response = client.patch(
        "/api/v1/auth/me",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "company_name": "Acme Corp",
            "country": "GB",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["first_name"] == "Ada"
    assert body["last_name"] == "Lovelace"
    assert body["company_name"] == "Acme Corp"
    assert body["country"] == "GB"


# --- Phase 24: change password (authenticated) ---


def test_change_password_succeeds_and_new_password_works(client):
    _verify_email(
        client,
        client.post(
            "/api/v1/auth/register",
            json=_register_payload(username="changepass", email="changepass@example.com"),
        ),
    )
    token = _login(client, "changepass", "Sup3rSecret!")

    response = client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "Sup3rSecret!",
            "new_password": "NewSecret1",
            "confirm_new_password": "NewSecret1",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200

    old_login = client.post(
        "/api/v1/auth/login", data={"username": "changepass", "password": "Sup3rSecret!"}
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/v1/auth/login", data={"username": "changepass", "password": "NewSecret1"}
    )
    assert new_login.status_code == 200


def test_change_password_rejects_wrong_current_password(client):
    _verify_email(
        client,
        client.post(
            "/api/v1/auth/register",
            json=_register_payload(username="changepass2", email="changepass2@example.com"),
        ),
    )
    token = _login(client, "changepass2", "Sup3rSecret!")

    response = client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "WrongPassword!",
            "new_password": "NewSecret1",
            "confirm_new_password": "NewSecret1",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CURRENT_PASSWORD"


def test_change_password_rejects_mismatched_confirmation(client):
    _verify_email(
        client,
        client.post(
            "/api/v1/auth/register",
            json=_register_payload(username="changepass3", email="changepass3@example.com"),
        ),
    )
    token = _login(client, "changepass3", "Sup3rSecret!")

    response = client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "Sup3rSecret!",
            "new_password": "NewSecret1",
            "confirm_new_password": "SomethingElse1",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_change_password_rejects_weak_new_password(client):
    _verify_email(
        client,
        client.post(
            "/api/v1/auth/register",
            json=_register_payload(username="changepass4", email="changepass4@example.com"),
        ),
    )
    token = _login(client, "changepass4", "Sup3rSecret!")

    response = client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "Sup3rSecret!",
            "new_password": "weakpass",
            "confirm_new_password": "weakpass",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_change_password_requires_authentication(client):
    response = client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "Sup3rSecret!",
            "new_password": "NewSecret1",
            "confirm_new_password": "NewSecret1",
        },
    )
    assert response.status_code == 401


def test_update_me_rejects_non_e164_phone_number(client):
    _verify_email(
        client,
        client.post(
            "/api/v1/auth/register",
            json=_register_payload(username="badphone", email="badphone@example.com"),
        ),
    )
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
    _verify_email(client, client.post("/api/v1/auth/register", json=_register_payload()))
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
    _verify_email(client, client.post("/api/v1/auth/register", json=_register_payload()))
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
    _verify_email(client, client.post("/api/v1/auth/register", json=_register_payload()))

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


# --- Phase 24: SaaS signup (no username field, new profile fields, email login) ---


def _saas_signup_payload(**overrides):
    """The new signup form's shape - deliberately has no `username` key at
    all (it's auto-derived from the email), unlike _register_payload()."""
    payload = {
        "email": "new.signup@example.com",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "mobile_number": "+14155552671",
        "company_name": "Acme Corp",
        "country": "GB",
        "password": "Sup3rSecret1",
        "confirm_password": "Sup3rSecret1",
    }
    payload.update(overrides)
    return payload


def test_register_without_username_auto_generates_one_from_email(client):
    response = client.post("/api/v1/auth/register", json=_saas_signup_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "new.signup"
    assert body["first_name"] == "Ada"
    assert body["last_name"] == "Lovelace"
    assert body["company_name"] == "Acme Corp"
    assert body["country"] == "GB"
    assert body["phone_number"] == "+14155552671"
    assert body["email_verified"] is False


def test_register_auto_generated_username_collision_gets_a_numeric_suffix(client):
    client.post(
        "/api/v1/auth/register",
        json=_saas_signup_payload(email="dupe@example.com"),
    )
    response = client.post(
        "/api/v1/auth/register",
        json=_saas_signup_payload(email="dupe@other-domain.com"),
    )
    assert response.status_code == 201
    assert response.json()["username"] == "dupe2"


def test_register_without_username_still_rejects_duplicate_email(client):
    client.post("/api/v1/auth/register", json=_saas_signup_payload())
    response = client.post("/api/v1/auth/register", json=_saas_signup_payload())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "USER_EXISTS"


def test_register_rejects_mismatched_confirm_password(client):
    response = client.post(
        "/api/v1/auth/register",
        json=_saas_signup_payload(confirm_password="SomethingElse1"),
    )
    assert response.status_code == 422


def test_register_rejects_invalid_mobile_number(client):
    response = client.post(
        "/api/v1/auth/register",
        json=_saas_signup_payload(mobile_number="not-a-phone-number"),
    )
    assert response.status_code == 422


def test_login_succeeds_with_email_instead_of_username(client):
    _verify_email(client, client.post("/api/v1/auth/register", json=_saas_signup_payload()))
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "new.signup@example.com", "password": "Sup3rSecret1"},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_still_succeeds_with_username_for_existing_style_registration(client):
    _verify_email(client, client.post("/api/v1/auth/register", json=_register_payload()))
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "jdoe", "password": "Sup3rSecret!"},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


# --- Phase 24: email verification gate ---


def test_login_is_blocked_before_email_is_verified(client):
    client.post("/api/v1/auth/register", json=_register_payload())
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "jdoe", "password": "Sup3rSecret!"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"


def test_verify_email_with_the_real_token_activates_login(client):
    register_response = client.post("/api/v1/auth/register", json=_register_payload())
    token = register_response.json()["verification_token"]

    verify_response = client.get("/api/v1/auth/verify-email", params={"token": token})
    assert verify_response.status_code == 200
    assert verify_response.json()["email_verified"] is True

    login_response = client.post(
        "/api/v1/auth/login",
        data={"username": "jdoe", "password": "Sup3rSecret!"},
    )
    assert login_response.status_code == 200


def test_verify_email_rejects_an_unknown_token(client):
    response = client.get("/api/v1/auth/verify-email", params={"token": "not-a-real-token"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_OR_EXPIRED_TOKEN"


def test_verify_email_rejects_an_expired_token(client, db_session):
    from datetime import datetime, timedelta

    register_response = client.post("/api/v1/auth/register", json=_register_payload())
    token = register_response.json()["verification_token"]

    user = db_session.query(User).filter(User.username == "jdoe").one()
    user.email_verification_expires_at = datetime.utcnow() - timedelta(hours=1)
    db_session.commit()

    response = client.get("/api/v1/auth/verify-email", params={"token": token})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_OR_EXPIRED_TOKEN"


def test_resend_verification_issues_a_new_token_invalidating_the_old_one(client, db_session):
    register_response = client.post("/api/v1/auth/register", json=_register_payload())
    old_token = register_response.json()["verification_token"]

    resend_response = client.post(
        "/api/v1/auth/resend-verification", json={"email": "jdoe@example.com"}
    )
    assert resend_response.status_code == 200

    # The pre-resend token was replaced - it must no longer verify.
    stale_response = client.get("/api/v1/auth/verify-email", params={"token": old_token})
    assert stale_response.status_code == 422

    db_session.expire_all()
    user = db_session.query(User).filter(User.username == "jdoe").one()
    assert user.email_verification_token_hash is not None
    assert not user.email_verified


def test_resend_verification_is_a_no_op_once_already_verified(client):
    register_response = client.post("/api/v1/auth/register", json=_register_payload())
    _verify_email(client, register_response)

    response = client.post(
        "/api/v1/auth/resend-verification", json={"email": "jdoe@example.com"}
    )
    assert response.status_code == 200

    login_response = client.post(
        "/api/v1/auth/login", data={"username": "jdoe", "password": "Sup3rSecret!"}
    )
    assert login_response.status_code == 200


def test_resend_verification_is_generic_for_an_unknown_email(client):
    response = client.post(
        "/api/v1/auth/resend-verification", json={"email": "nobody-registered@example.com"}
    )
    assert response.status_code == 200
    assert response.json()["email_verified"] is False


# --- Phase 24: forgot / reset password ---


def _extract_token_from_logged_link(caplog, needle: str) -> str:
    """Forgot-password never returns the raw token over the API (unlike
    register/verify-email) - doing so would let a caller distinguish a
    real account from a fake one by whether a token came back, defeating
    the whole point of always returning a generic response. So a test
    proving the real, logged link actually works has to get the token the
    same way a real developer would in this environment: from the log
    line - not from a bypass or a hand-constructed value."""
    import re

    record = next(r for r in caplog.records if needle in r.getMessage())
    match = re.search(r"token=([^&\s]+)", record.getMessage())
    assert match, f"no token found in logged message: {record.getMessage()}"
    return match.group(1)


def test_forgot_password_and_reset_actually_changes_the_password(client, caplog):
    import logging

    register_response = client.post("/api/v1/auth/register", json=_register_payload())
    _verify_email(client, register_response)

    with caplog.at_level(logging.INFO, logger="auth"):
        response = client.post(
            "/api/v1/auth/forgot-password", json={"email": "jdoe@example.com"}
        )
    assert response.status_code == 200
    token = _extract_token_from_logged_link(caplog, "Password reset link")

    reset_response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "NewSecret1", "confirm_new_password": "NewSecret1"},
    )
    assert reset_response.status_code == 200

    old_password_login = client.post(
        "/api/v1/auth/login", data={"username": "jdoe", "password": "Sup3rSecret!"}
    )
    assert old_password_login.status_code == 401

    new_password_login = client.post(
        "/api/v1/auth/login", data={"username": "jdoe", "password": "NewSecret1"}
    )
    assert new_password_login.status_code == 200


def test_forgot_password_is_generic_for_an_unknown_email(client):
    response = client.post(
        "/api/v1/auth/forgot-password", json={"email": "nobody-registered@example.com"}
    )
    assert response.status_code == 200


def test_reset_password_rejects_an_unknown_token(client):
    response = client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": "not-a-real-token",
            "new_password": "NewSecret1",
            "confirm_new_password": "NewSecret1",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_OR_EXPIRED_TOKEN"


def test_reset_password_rejects_an_expired_token(client, db_session):
    from datetime import datetime, timedelta

    client.post("/api/v1/auth/register", json=_register_payload())

    user = db_session.query(User).filter(User.username == "jdoe").one()
    from app.utils.tokens import generate_token, hash_token

    raw_token = generate_token()
    user.password_reset_token_hash = hash_token(raw_token)
    user.password_reset_expires_at = datetime.utcnow() - timedelta(hours=1)
    db_session.commit()

    response = client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": raw_token,
            "new_password": "NewSecret1",
            "confirm_new_password": "NewSecret1",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_OR_EXPIRED_TOKEN"


def test_reset_password_rejects_mismatched_confirmation(client):
    response = client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": "irrelevant-fails-validation-first",
            "new_password": "NewSecret1",
            "confirm_new_password": "SomethingElse1",
        },
    )
    assert response.status_code == 422


def test_reset_password_rejects_a_weak_new_password(client):
    response = client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": "irrelevant-fails-validation-first",
            "new_password": "weakpass",
            "confirm_new_password": "weakpass",
        },
    )
    assert response.status_code == 422


# --- Phase 24: Remember Me ---


def _decode_refresh_token(token: str) -> dict:
    from app.authentication.jwt_handler import TokenType, decode_token

    return decode_token(token, TokenType.REFRESH)


def test_login_without_remember_me_issues_the_default_short_refresh_token(client):
    _verify_email(client, client.post("/api/v1/auth/register", json=_register_payload()))
    response = client.post(
        "/api/v1/auth/login", data={"username": "jdoe", "password": "Sup3rSecret!"}
    )
    payload = _decode_refresh_token(response.json()["refresh_token"])
    assert payload["remember_me"] is False
    lifetime_days = (payload["exp"] - payload["iat"]) / 86400
    assert 6.9 < lifetime_days < 7.1


def test_login_with_remember_me_issues_a_long_lived_refresh_token(client):
    _verify_email(client, client.post("/api/v1/auth/register", json=_register_payload()))
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "jdoe", "password": "Sup3rSecret!", "remember_me": "true"},
    )
    payload = _decode_refresh_token(response.json()["refresh_token"])
    assert payload["remember_me"] is True
    lifetime_days = (payload["exp"] - payload["iat"]) / 86400
    assert 29.9 < lifetime_days < 30.1


def test_refresh_carries_remember_me_forward_to_the_new_refresh_token(client):
    _verify_email(client, client.post("/api/v1/auth/register", json=_register_payload()))
    login_response = client.post(
        "/api/v1/auth/login",
        data={"username": "jdoe", "password": "Sup3rSecret!", "remember_me": "true"},
    )
    original_refresh_token = login_response.json()["refresh_token"]

    refresh_response = client.post(
        "/api/v1/auth/refresh", params={"refresh_token": original_refresh_token}
    )
    assert refresh_response.status_code == 200

    new_payload = _decode_refresh_token(refresh_response.json()["refresh_token"])
    assert new_payload["remember_me"] is True
    lifetime_days = (new_payload["exp"] - new_payload["iat"]) / 86400
    assert 29.9 < lifetime_days < 30.1
