"""Telegram delivery via the Bot API's `sendMessage` method.

When `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` are unset, `send` logs instead of
calling the API - see `email_notifier.py` for why that fallback exists.
"""
import httpx

from app.config.settings import get_settings
from app.utils.logger import get_logger

logger = get_logger("notifications.telegram")


def send_telegram_message(text: str) -> bool:
    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        logger.info("Telegram bot not configured; would send: %s", text)
        return False

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    response = httpx.post(
        url, json={"chat_id": settings.TELEGRAM_CHAT_ID, "text": text}, timeout=10
    )
    response.raise_for_status()

    logger.info("Sent Telegram message: %s", text)
    return True
