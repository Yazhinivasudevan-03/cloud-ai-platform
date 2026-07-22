"""Telegram delivery via the Bot API's `sendMessage` method.

When `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` are unset, `send` logs instead of
calling the API - see `email_notifier.py` for why that fallback exists.
"""
import httpx

from app.config.settings import get_settings
from app.utils.logger import get_logger
from app.utils.retry import http_retry

logger = get_logger("notifications.telegram")


@http_retry
def _post(bot_token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    response = httpx.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
    response.raise_for_status()


def send_telegram_message(text: str) -> bool:
    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        logger.info("Telegram bot not configured; would send: %s", text)
        return False

    try:
        _post(settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_CHAT_ID, text)
    except Exception:
        # Retries (see app/utils/retry.py) are already exhausted - degrade
        # gracefully rather than crashing the whole alert evaluation batch.
        logger.exception("Failed to send Telegram message after retries")
        return False

    logger.info("Sent Telegram message: %s", text)
    return True
