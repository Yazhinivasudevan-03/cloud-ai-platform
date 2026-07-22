"""Slack delivery via an Incoming Webhook.

When `SLACK_WEBHOOK_URL` is unset, `send` logs instead of posting - see
`email_notifier.py` for why that fallback exists.
"""
import httpx

from app.config.settings import get_settings
from app.utils.logger import get_logger
from app.utils.retry import http_retry

logger = get_logger("notifications.slack")


@http_retry
def _post(webhook_url: str, text: str) -> None:
    response = httpx.post(webhook_url, json={"text": text}, timeout=10)
    response.raise_for_status()


def send_slack_message(text: str) -> bool:
    settings = get_settings()
    if not settings.SLACK_WEBHOOK_URL:
        logger.info("Slack webhook not configured; would post: %s", text)
        return False

    try:
        _post(settings.SLACK_WEBHOOK_URL, text)
    except Exception:
        # Retries (see app/utils/retry.py) are already exhausted by this
        # point - degrade gracefully rather than letting one flaky webhook
        # crash the whole alert evaluation batch.
        logger.exception("Failed to post Slack message after retries")
        return False

    logger.info("Posted Slack message: %s", text)
    return True
