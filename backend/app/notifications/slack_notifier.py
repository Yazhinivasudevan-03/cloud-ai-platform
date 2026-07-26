"""Slack delivery via an Incoming Webhook.

When no webhook URL is configured (globally or per-user), `send` logs
instead of posting - see `email_notifier.py` for why that fallback exists.
"""
import httpx

from app.config.settings import get_settings
from app.utils.logger import get_logger
from app.utils.retry import http_retry

logger = get_logger("notifications.slack")

# Same real, distinct reason codes as email_notifier.py (Phase 23 follow-up).
REASON_NOT_CONFIGURED = "not_configured"
REASON_SENT = "sent"
REASON_AUTH_FAILED = "auth_failed"
REASON_UNREACHABLE = "unreachable"
REASON_INVALID_RECIPIENT = "invalid_recipient"
REASON_FAILED = "failed"


@http_retry
def _post(webhook_url: str, text: str) -> None:
    response = httpx.post(webhook_url, json={"text": text}, timeout=10)
    response.raise_for_status()


def send_slack_message_with_reason(text: str, webhook_url: str | None = None) -> tuple[bool, str]:
    """`webhook_url` lets a caller (e.g. a per-user NotificationSetting,
    Phase 20) override the platform-wide webhook configured in settings.
    Returns (sent, reason) - see email_notifier.py's REASON_* constants."""
    settings = get_settings()
    webhook_url = webhook_url or settings.SLACK_WEBHOOK_URL
    if not webhook_url:
        logger.info("Slack webhook not configured; would post: %s", text)
        return False, REASON_NOT_CONFIGURED

    try:
        _post(webhook_url, text)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (401, 403):
            logger.exception("Slack rejected the configured webhook")
            return False, REASON_AUTH_FAILED
        if status == 404:
            logger.exception("Slack webhook URL not found (revoked/invalid)")
            return False, REASON_INVALID_RECIPIENT
        logger.exception("Slack returned an error")
        return False, REASON_FAILED
    except httpx.TransportError:
        logger.exception("Slack unreachable")
        return False, REASON_UNREACHABLE
    except Exception:
        # Retries (see app/utils/retry.py) are already exhausted by this
        # point - degrade gracefully rather than letting one flaky webhook
        # crash the whole alert evaluation batch.
        logger.exception("Failed to post Slack message after retries")
        return False, REASON_FAILED

    logger.info("Posted Slack message: %s", text)
    return True, REASON_SENT


def send_slack_message(text: str, webhook_url: str | None = None) -> bool:
    """See `send_slack_message_with_reason` for *why* a False came back."""
    sent, _reason = send_slack_message_with_reason(text, webhook_url)
    return sent
