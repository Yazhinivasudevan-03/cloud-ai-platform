"""Telegram delivery via the Bot API's `sendMessage` method.

When no bot token/chat ID are configured (globally or per-user), `send`
logs instead of calling the API - see `email_notifier.py` for why that
fallback exists.
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


def send_telegram_message(
    text: str, bot_token: str | None = None, chat_id: str | None = None
) -> bool:
    """`bot_token`/`chat_id` let a caller (e.g. a per-user NotificationSetting,
    Phase 20) override the platform-wide bot/chat configured in settings -
    a user only needs to supply their own chat ID to receive alerts through
    a shared bot, without running their own."""
    settings = get_settings()
    bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
    chat_id = chat_id or settings.TELEGRAM_CHAT_ID
    if not bot_token or not chat_id:
        logger.info("Telegram bot not configured; would send: %s", text)
        return False

    try:
        _post(bot_token, chat_id, text)
    except Exception:
        # Retries (see app/utils/retry.py) are already exhausted - degrade
        # gracefully rather than crashing the whole alert evaluation batch.
        logger.exception("Failed to send Telegram message after retries")
        return False

    logger.info("Sent Telegram message: %s", text)
    return True
