"""Unit tests for the notification channel integrations.

No real SMTP server/Slack workspace/Telegram bot is available in this
environment, so these tests verify the *logic* honestly: correct behavior
when unconfigured (log and return False, never raise), and correct calls
made to the underlying client when configured (mocked, not live) - see
docs/PHASE_5.md for the explicit disclosure that live external delivery was
not verified end-to-end.
"""
import smtplib
from unittest.mock import MagicMock, patch

import httpx

from app.config.settings import get_settings
from app.notifications.email_notifier import send_email
from app.notifications.slack_notifier import send_slack_message
from app.notifications.sms_notifier import send_sms
from app.notifications.teams_notifier import send_teams_message
from app.notifications.telegram_notifier import send_telegram_message


def test_send_email_returns_false_and_logs_when_unconfigured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "SMTP_HOST", "")

    result = send_email("someone@example.com", "subject", "body")

    assert result is False


def test_send_email_calls_smtp_when_configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_USER", "user")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "pass")
    monkeypatch.setattr(settings, "SMTP_FROM_ADDRESS", "alerts@example.com")
    monkeypatch.setattr(settings, "SMTP_USE_TLS", True)

    mock_smtp_instance = MagicMock()
    mock_smtp_context = MagicMock()
    mock_smtp_context.__enter__.return_value = mock_smtp_instance
    mock_smtp_context.__exit__.return_value = False

    with patch("app.notifications.email_notifier.smtplib.SMTP", return_value=mock_smtp_context) as mock_smtp_cls:
        result = send_email("someone@example.com", "Test Subject", "Test body")

    assert result is True
    mock_smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=10)
    mock_smtp_instance.starttls.assert_called_once()
    mock_smtp_instance.login.assert_called_once_with("user", "pass")
    mock_smtp_instance.send_message.assert_called_once()


def test_send_slack_message_returns_false_when_unconfigured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", "")

    result = send_slack_message("hello")

    assert result is False


def test_send_slack_message_posts_to_webhook_when_configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", "https://hooks.slack.example/webhook")

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None

    with patch("app.notifications.slack_notifier.httpx.post", return_value=mock_response) as mock_post:
        result = send_slack_message("hello from the alert engine")

    assert result is True
    mock_post.assert_called_once_with(
        "https://hooks.slack.example/webhook",
        json={"text": "hello from the alert engine"},
        timeout=10,
    )


def test_send_slack_message_per_user_override_wins_over_global_setting(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", "https://hooks.slack.example/global-webhook")

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None

    with patch("app.notifications.slack_notifier.httpx.post", return_value=mock_response) as mock_post:
        result = send_slack_message("hello", webhook_url="https://hooks.slack.example/personal-webhook")

    assert result is True
    mock_post.assert_called_once_with(
        "https://hooks.slack.example/personal-webhook",
        json={"text": "hello"},
        timeout=10,
    )


def test_send_slack_message_falls_back_to_global_setting_when_no_override(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", "https://hooks.slack.example/global-webhook")

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None

    with patch("app.notifications.slack_notifier.httpx.post", return_value=mock_response) as mock_post:
        result = send_slack_message("hello", webhook_url=None)

    assert result is True
    mock_post.assert_called_once_with(
        "https://hooks.slack.example/global-webhook", json={"text": "hello"}, timeout=10
    )


def test_send_telegram_message_returns_false_when_unconfigured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "")

    result = send_telegram_message("hello")

    assert result is False


def test_send_telegram_message_calls_bot_api_when_configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "999")

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None

    with patch("app.notifications.telegram_notifier.httpx.post", return_value=mock_response) as mock_post:
        result = send_telegram_message("hello from the alert engine")

    assert result is True
    mock_post.assert_called_once_with(
        "https://api.telegram.org/bot123:abc/sendMessage",
        json={"chat_id": "999", "text": "hello from the alert engine"},
        timeout=10,
    )


def test_send_telegram_message_per_user_override_wins_over_global_setting(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "global-token")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "global-chat")

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None

    with patch("app.notifications.telegram_notifier.httpx.post", return_value=mock_response) as mock_post:
        result = send_telegram_message("hello", bot_token="personal-token", chat_id="personal-chat")

    assert result is True
    mock_post.assert_called_once_with(
        "https://api.telegram.org/botpersonal-token/sendMessage",
        json={"chat_id": "personal-chat", "text": "hello"},
        timeout=10,
    )


def test_send_sms_returns_false_when_unconfigured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "")
    monkeypatch.setattr(settings, "TWILIO_FROM_NUMBER", "")

    result = send_sms("+14155552671", "hello")

    assert result is False


def test_send_sms_returns_false_when_user_has_no_phone_number(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "ACxxxx")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "secret")
    monkeypatch.setattr(settings, "TWILIO_FROM_NUMBER", "+15005550006")

    with patch("app.notifications.sms_notifier.httpx.post") as mock_post:
        result = send_sms(None, "hello")

    assert result is False
    mock_post.assert_not_called()


def test_send_sms_calls_twilio_api_when_configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "ACxxxx")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "secret")
    monkeypatch.setattr(settings, "TWILIO_FROM_NUMBER", "+15005550006")

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None

    with patch("app.notifications.sms_notifier.httpx.post", return_value=mock_response) as mock_post:
        result = send_sms("+14155552671", "hello from the alert engine")

    assert result is True
    mock_post.assert_called_once_with(
        "https://api.twilio.com/2010-04-01/Accounts/ACxxxx/Messages.json",
        auth=("ACxxxx", "secret"),
        data={"From": "+15005550006", "To": "+14155552671", "Body": "hello from the alert engine"},
        timeout=10,
    )


def test_send_sms_retries_on_transient_error_then_succeeds(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "ACxxxx")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "secret")
    monkeypatch.setattr(settings, "TWILIO_FROM_NUMBER", "+15005550006")

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None

    with patch(
        "app.notifications.sms_notifier.httpx.post",
        side_effect=[httpx.ConnectError("connection refused"), mock_response],
    ) as mock_post:
        result = send_sms("+14155552671", "hello")

    assert result is True
    assert mock_post.call_count == 2


def test_send_sms_returns_false_after_retries_exhausted(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "ACxxxx")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "secret")
    monkeypatch.setattr(settings, "TWILIO_FROM_NUMBER", "+15005550006")

    with patch(
        "app.notifications.sms_notifier.httpx.post",
        side_effect=httpx.ConnectError("connection refused"),
    ) as mock_post:
        result = send_sms("+14155552671", "hello")

    assert result is False
    assert mock_post.call_count == 3


def test_send_sms_does_not_retry_bad_credentials(monkeypatch):
    """A 401 (bad Account SID/Auth Token) is a config error, not a
    transient failure - retrying it 3 times would only waste time."""
    settings = get_settings()
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "ACxxxx")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "wrong-token")
    monkeypatch.setattr(settings, "TWILIO_FROM_NUMBER", "+15005550006")

    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Unauthorized", request=MagicMock(), response=mock_response
    )

    with patch("app.notifications.sms_notifier.httpx.post", return_value=mock_response) as mock_post:
        result = send_sms("+14155552671", "hello")

    assert result is False
    assert mock_post.call_count == 1


def test_send_teams_message_returns_false_when_no_webhook_given():
    result = send_teams_message("hello", webhook_url=None)
    assert result is False


def test_send_teams_message_posts_to_webhook_when_given():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None

    with patch("app.notifications.teams_notifier.httpx.post", return_value=mock_response) as mock_post:
        result = send_teams_message("hello", webhook_url="https://outlook.office.example/webhook")

    assert result is True
    mock_post.assert_called_once_with(
        "https://outlook.office.example/webhook", json={"text": "hello"}, timeout=10
    )


# --- Retry/backoff on transient failures ------------------------------------


def test_send_slack_message_retries_on_transient_error_then_succeeds(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", "https://hooks.slack.example/webhook")

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None

    with patch(
        "app.notifications.slack_notifier.httpx.post",
        side_effect=[httpx.ConnectError("connection refused"), mock_response],
    ) as mock_post:
        result = send_slack_message("hello")

    assert result is True
    assert mock_post.call_count == 2  # failed once, retried, succeeded


def test_send_slack_message_returns_false_after_retries_exhausted(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", "https://hooks.slack.example/webhook")

    with patch(
        "app.notifications.slack_notifier.httpx.post",
        side_effect=httpx.ConnectError("connection refused"),
    ) as mock_post:
        result = send_slack_message("hello")

    assert result is False  # degrades gracefully, never raises
    assert mock_post.call_count == 3  # exhausted all 3 attempts


def test_send_slack_message_does_not_retry_a_bad_webhook_url(monkeypatch):
    """A 4xx (e.g. webhook deactivated/not found) is a config error, not a
    transient failure - retrying it 3 times would only waste time."""
    settings = get_settings()
    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", "https://hooks.slack.example/webhook")

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not Found", request=MagicMock(), response=mock_response
    )

    with patch("app.notifications.slack_notifier.httpx.post", return_value=mock_response) as mock_post:
        result = send_slack_message("hello")

    assert result is False
    assert mock_post.call_count == 1  # no retry for a 4xx


def test_send_email_retries_on_transient_error_then_succeeds(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_USER", "")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "")
    monkeypatch.setattr(settings, "SMTP_FROM_ADDRESS", "alerts@example.com")
    monkeypatch.setattr(settings, "SMTP_USE_TLS", False)

    mock_smtp_instance = MagicMock()
    mock_smtp_context = MagicMock()
    mock_smtp_context.__enter__.return_value = mock_smtp_instance
    mock_smtp_context.__exit__.return_value = False

    with patch(
        "app.notifications.email_notifier.smtplib.SMTP",
        side_effect=[ConnectionRefusedError("connection refused"), mock_smtp_context],
    ) as mock_smtp_cls:
        result = send_email("someone@example.com", "subject", "body")

    assert result is True
    assert mock_smtp_cls.call_count == 2


def test_send_email_does_not_retry_authentication_failure(monkeypatch):
    """A bad username/password is a permanent config error - retrying it
    3 times just wastes time before failing anyway."""
    settings = get_settings()
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_USER", "user")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "wrong-password")
    monkeypatch.setattr(settings, "SMTP_FROM_ADDRESS", "alerts@example.com")
    monkeypatch.setattr(settings, "SMTP_USE_TLS", False)

    with patch(
        "app.notifications.email_notifier.smtplib.SMTP",
        side_effect=smtplib.SMTPAuthenticationError(535, b"Authentication failed"),
    ) as mock_smtp_cls:
        result = send_email("someone@example.com", "subject", "body")

    assert result is False
    assert mock_smtp_cls.call_count == 1
