"""Slack delivery via an Incoming Webhook.

When `SLACK_WEBHOOK_URL` is unset, `send` logs instead of posting - see
`email_notifier.py` for why that fallback exists.
"""
import httpx

from app.config.settings import get_settings
from app.utils.logger import get_logger

logger = get_logger("notifications.slack")


def send_slack_message(text: str) -> bool:
    settings = get_settings()
    if not settings.SLACK_WEBHOOK_URL:
        logger.info("Slack webhook not configured; would post: %s", text)
        return False

    response = httpx.post(settings.SLACK_WEBHOOK_URL, json={"text": text}, timeout=10)
    response.raise_for_status()

    logger.info("Posted Slack message: %s", text)
    return True
