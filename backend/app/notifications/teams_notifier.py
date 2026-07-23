"""Microsoft Teams delivery via an Incoming Webhook (Office 365 Connector
format) - structurally identical to slack_notifier.py, just a different
provider's webhook JSON shape and no platform-wide fallback setting: Teams
is optional and per-user only (see NotificationSetting), so there is
nothing to fall back to when a user hasn't configured one.
"""
import httpx

from app.utils.logger import get_logger
from app.utils.retry import http_retry

logger = get_logger("notifications.teams")


@http_retry
def _post(webhook_url: str, text: str) -> None:
    response = httpx.post(webhook_url, json={"text": text}, timeout=10)
    response.raise_for_status()


def send_teams_message(text: str, webhook_url: str | None) -> bool:
    if not webhook_url:
        logger.info("Teams webhook not configured; would post: %s", text)
        return False

    try:
        _post(webhook_url, text)
    except Exception:
        # Retries (see app/utils/retry.py) are already exhausted - degrade
        # gracefully rather than crashing the whole alert evaluation batch.
        logger.exception("Failed to post Teams message after retries")
        return False

    logger.info("Posted Teams message: %s", text)
    return True
