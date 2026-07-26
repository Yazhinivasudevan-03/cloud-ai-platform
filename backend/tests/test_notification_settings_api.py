"""Integration tests for the self-service Notification Settings API
(Phase 20) - defaults, updates, credential write-only behavior, and the
real test-notification endpoint (mocked at the HTTP-client boundary, same
convention as test_notifiers.py)."""
from unittest.mock import MagicMock, patch

from app.models.notification_setting import NotificationSetting


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_get_notification_settings_returns_defaults_when_never_configured(client, make_user_with_role):
    token = make_user_with_role("notif_settings_a")

    response = client.get("/api/v1/notification-settings", headers=_auth_header(token))

    assert response.status_code == 200
    body = response.json()
    assert body["email_enabled"] is True
    assert body["sms_enabled"] is False
    assert body["telegram_enabled"] is False
    assert body["slack_enabled"] is False
    assert body["teams_enabled"] is False
    assert body["instant_alerts_enabled"] is True
    assert body["daily_summary_enabled"] is False
    assert body["timezone"] == "UTC"
    assert body["telegram_bot_token_configured"] is False
    assert body["slack_webhook_configured"] is False


def test_get_notification_settings_requires_authentication(client):
    response = client.get("/api/v1/notification-settings")
    assert response.status_code == 401


def test_update_notification_settings_persists_toggles_and_dnd(client, make_user_with_role):
    token = make_user_with_role("notif_settings_b")

    response = client.put(
        "/api/v1/notification-settings",
        json={
            "sms_enabled": True,
            "slack_enabled": True,
            "dnd_start_time": "22:00:00",
            "dnd_end_time": "07:00:00",
            "timezone": "Europe/London",
        },
        headers=_auth_header(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sms_enabled"] is True
    assert body["slack_enabled"] is True
    assert body["dnd_start_time"] == "22:00:00"
    assert body["dnd_end_time"] == "07:00:00"
    assert body["timezone"] == "Europe/London"
    assert body["email_enabled"] is True  # untouched field keeps its default

    # Persisted, not just echoed back - a fresh GET reflects the same state.
    get_response = client.get("/api/v1/notification-settings", headers=_auth_header(token))
    assert get_response.json()["timezone"] == "Europe/London"


def test_update_notification_settings_stores_credentials_encrypted_and_write_only(
    client, make_user_with_role, db_session
):
    token = make_user_with_role("notif_settings_c")

    response = client.put(
        "/api/v1/notification-settings",
        json={
            "telegram_bot_token": "123456:abcdef",
            "telegram_chat_id": "987654",
            "slack_webhook_url": "https://hooks.slack.example/webhook",
        },
        headers=_auth_header(token),
    )

    assert response.status_code == 200
    body = response.json()
    # Never echoed back in plaintext - only a boolean "is it set" flag.
    assert "telegram_bot_token" not in body
    assert "slack_webhook_url" not in body
    assert body["telegram_bot_token_configured"] is True
    assert body["telegram_chat_id_configured"] is True
    assert body["slack_webhook_configured"] is True

    setting = db_session.query(NotificationSetting).one()
    assert setting.credentials_encrypted is not None
    assert "123456:abcdef" not in setting.credentials_encrypted  # genuinely encrypted, not plaintext
    assert "hooks.slack.example" not in setting.credentials_encrypted


def test_clearing_a_credential_with_empty_string_unconfigures_it(client, make_user_with_role):
    token = make_user_with_role("notif_settings_d")
    client.put(
        "/api/v1/notification-settings",
        json={"telegram_bot_token": "123456:abcdef", "telegram_chat_id": "987654"},
        headers=_auth_header(token),
    )

    response = client.put(
        "/api/v1/notification-settings",
        json={"telegram_bot_token": ""},
        headers=_auth_header(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["telegram_bot_token_configured"] is False
    assert body["telegram_chat_id_configured"] is True  # untouched credential survives


def test_test_notification_sends_through_enabled_channels_only(client, make_user_with_role):
    token = make_user_with_role("notif_settings_e")
    client.put(
        "/api/v1/notification-settings",
        json={
            "slack_enabled": True,
            "sms_enabled": False,
            "telegram_enabled": False,
            "slack_webhook_url": "https://hooks.slack.example/personal-webhook",
        },
        headers=_auth_header(token),
    )

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    with patch("app.notifications.slack_notifier.httpx.post", return_value=mock_response) as mock_slack_post:
        response = client.post("/api/v1/notification-settings/test", headers=_auth_header(token))

    assert response.status_code == 200
    body = response.json()
    assert body["slack_sent"] is True
    assert body["slack_reason"] == "sent"
    assert body["sms_sent"] is None  # disabled channel - never attempted
    assert body["sms_reason"] is None
    assert body["telegram_sent"] is None
    # email_enabled defaults to True, so it's attempted - but SMTP isn't
    # configured in this test environment, so it's correctly False (logged,
    # not sent), not None. The reason is now specific, not a generic "failed".
    assert body["email_sent"] is False
    assert body["email_reason"] == "not_configured"
    mock_slack_post.assert_called_once()


# --- Personal contact info + alert preferences (Phase 23) -------------------


def test_get_notification_settings_defaults_include_new_contact_and_preference_fields(
    client, make_user_with_role
):
    token = make_user_with_role("notif_settings_f")

    response = client.get("/api/v1/notification-settings", headers=_auth_header(token))

    assert response.status_code == 200
    body = response.json()
    assert body["secondary_email"] is None
    assert body["country_code"] is None
    assert body["telegram_username"] is None
    assert body["notification_language"] == "en"
    assert set(body["alert_preferences"].keys()) == {
        "cpu", "memory", "disk", "network", "storage", "cloud_usage", "cloud_cost",
        "api_latency", "error_rate", "pod_restart", "security",
        "node_failure", "container_failure", "ai_prediction", "resource_optimization",
    }
    assert body["alert_preferences"]["cpu"] == {
        "enabled": True, "warning": True, "critical": True, "saturated": True,
    }


def test_update_notification_settings_persists_contact_info(client, make_user_with_role):
    token = make_user_with_role("notif_settings_g")

    response = client.put(
        "/api/v1/notification-settings",
        json={
            "secondary_email": "backup@example.com",
            "country_code": "+44",
            "telegram_username": "@jdoe",
            "notification_language": "fr",
        },
        headers=_auth_header(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["secondary_email"] == "backup@example.com"
    assert body["country_code"] == "+44"
    assert body["telegram_username"] == "@jdoe"
    assert body["notification_language"] == "fr"

    get_response = client.get("/api/v1/notification-settings", headers=_auth_header(token))
    assert get_response.json()["secondary_email"] == "backup@example.com"


def test_update_notification_settings_rejects_an_invalid_secondary_email(client, make_user_with_role):
    token = make_user_with_role("notif_settings_h")

    response = client.put(
        "/api/v1/notification-settings",
        json={"secondary_email": "not-an-email"},
        headers=_auth_header(token),
    )

    assert response.status_code == 422


def test_update_alert_preferences_partially_and_others_stay_at_default(client, make_user_with_role):
    token = make_user_with_role("notif_settings_i")

    response = client.put(
        "/api/v1/notification-settings",
        json={"alert_preferences": {"cpu": {"enabled": True, "warning": False, "critical": True, "saturated": True}}},
        headers=_auth_header(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["alert_preferences"]["cpu"]["warning"] is False
    assert body["alert_preferences"]["cpu"]["critical"] is True
    assert body["alert_preferences"]["memory"]["enabled"] is True  # untouched category still defaults enabled
    assert body["alert_preferences"]["node_failure"]["enabled"] is True

    # A second, unrelated update must not clobber the first one's change.
    second = client.put(
        "/api/v1/notification-settings",
        json={"alert_preferences": {"node_failure": {"enabled": False}}},
        headers=_auth_header(token),
    )
    assert second.json()["alert_preferences"]["cpu"]["warning"] is False
    assert second.json()["alert_preferences"]["node_failure"]["enabled"] is False


def test_test_notification_also_sends_to_secondary_email(client, make_user_with_role):
    token = make_user_with_role("notif_settings_j")
    client.put(
        "/api/v1/notification-settings",
        json={"email_enabled": True, "secondary_email": "backup@example.com"},
        headers=_auth_header(token),
    )

    response = client.post("/api/v1/notification-settings/test", headers=_auth_header(token))

    assert response.status_code == 200
    body = response.json()
    assert body["email_sent"] is False  # SMTP not configured in this test env - logged, not sent
    assert body["email_reason"] == "not_configured"
    assert body["secondary_email_sent"] is False  # attempted too, same reason
    assert body["secondary_email_reason"] == "not_configured"
