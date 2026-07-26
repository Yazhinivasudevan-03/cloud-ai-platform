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

# Same real, distinct reason codes as email_notifier.py (Phase 23 follow-up).
REASON_NOT_CONFIGURED = "not_configured"
REASON_SENT = "sent"
REASON_AUTH_FAILED = "auth_failed"
REASON_UNREACHABLE = "unreachable"
REASON_INVALID_RECIPIENT = "invalid_recipient"
REASON_FAILED = "failed"


@http_retry
def _post(bot_token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    response = httpx.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
    response.raise_for_status()


def send_telegram_message_with_reason(
    text: str, bot_token: str | None = None, chat_id: str | None = None
) -> tuple[bool, str]:
    """`bot_token`/`chat_id` let a caller (e.g. a per-user NotificationSetting,
    Phase 20) override the platform-wide bot/chat configured in settings.
    Returns (sent, reason) - see email_notifier.py's REASON_* constants."""
    settings = get_settings()
    bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
    chat_id = chat_id or settings.TELEGRAM_CHAT_ID
    if not bot_token or not chat_id:
        logger.info("Telegram bot not configured; would send: %s", text)
        return False, REASON_NOT_CONFIGURED

    try:
        _post(bot_token, chat_id, text)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (401, 403):
            logger.exception("Telegram rejected the configured bot token")
            return False, REASON_AUTH_FAILED
        if status == 400:
            logger.exception("Telegram rejected the chat ID %s", chat_id)
            return False, REASON_INVALID_RECIPIENT
        logger.exception("Telegram returned an error")
        return False, REASON_FAILED
    except httpx.TransportError:
        logger.exception("Telegram API unreachable")
        return False, REASON_UNREACHABLE
    except Exception:
        # Retries (see app/utils/retry.py) are already exhausted - degrade
        # gracefully rather than crashing the whole alert evaluation batch.
        logger.exception("Failed to send Telegram message after retries")
        return False, REASON_FAILED

    logger.info("Sent Telegram message: %s", text)
    return True, REASON_SENT


def send_telegram_message(
    text: str, bot_token: str | None = None, chat_id: str | None = None
) -> bool:
    """See `send_telegram_message_with_reason` for *why* a False came back."""
    sent, _reason = send_telegram_message_with_reason(text, bot_token, chat_id)
    return sent
