"""Unit tests for the notification channel integrations.

No real SMTP server/Slack workspace/Telegram bot is available in this
environment, so these tests verify the *logic* honestly: correct behavior
when unconfigured (log and return False, never raise), and correct calls
made to the underlying client when configured (mocked, not live) - see
docs/PHASE_5.md for the explicit disclosure that live external delivery was
not verified end-to-end.
"""
from unittest.mock import MagicMock, patch

from app.config.settings import get_settings
from app.notifications.email_notifier import send_email
from app.notifications.slack_notifier import send_slack_message
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
