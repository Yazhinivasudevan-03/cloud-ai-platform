"""SMS delivery via the Twilio REST API's Messages resource.

Uses `httpx` directly against Twilio's plain REST endpoint rather than
the `twilio` SDK, mirroring `slack_notifier.py`/`telegram_notifier.py`
exactly (both are also thin `httpx` calls against their provider's REST
API, not an SDK) - there is no meaningful advantage to a whole extra
dependency for what is a single authenticated POST.

When `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN`/`TWILIO_FROM_NUMBER` are
unset, or the target user has no `phone_number`, `send_sms` logs instead
of calling the API - see `email_notifier.py` for why that fallback exists.
"""
import httpx

from app.config.settings import get_settings
from app.utils.logger import get_logger
from app.utils.retry import http_retry

logger = get_logger("notifications.sms")

_TWILIO_MESSAGES_URL = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

# Same real, distinct reason codes as email_notifier.py (Phase 23 follow-up).
REASON_NOT_CONFIGURED = "not_configured"
REASON_NO_RECIPIENT = "no_recipient"
REASON_SENT = "sent"
REASON_AUTH_FAILED = "auth_failed"
REASON_UNREACHABLE = "unreachable"
REASON_INVALID_RECIPIENT = "invalid_recipient"
REASON_FAILED = "failed"


@http_retry
def _post(account_sid: str, auth_token: str, from_number: str, to_number: str, body: str) -> None:
    url = _TWILIO_MESSAGES_URL.format(account_sid=account_sid)
    response = httpx.post(
        url,
        auth=(account_sid, auth_token),
        data={"From": from_number, "To": to_number, "Body": body},
        timeout=10,
    )
    response.raise_for_status()


def send_sms_with_reason(to_number: str | None, text: str) -> tuple[bool, str]:
    """Send an SMS, returning (sent, reason). `reason` is one of the
    REASON_* constants above, always reflecting what genuinely happened."""
    settings = get_settings()
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_FROM_NUMBER:
        logger.info("Twilio not configured; would send SMS to %s: %s", to_number, text)
        return False, REASON_NOT_CONFIGURED
    if not to_number:
        logger.info("User has no phone_number on file; would send SMS: %s", text)
        return False, REASON_NO_RECIPIENT

    try:
        _post(
            settings.TWILIO_ACCOUNT_SID,
            settings.TWILIO_AUTH_TOKEN,
            settings.TWILIO_FROM_NUMBER,
            to_number,
            text,
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (401, 403):
            logger.exception("Twilio rejected the configured credentials")
            return False, REASON_AUTH_FAILED
        if status == 400:
            logger.exception("Twilio rejected the recipient number %s", to_number)
            return False, REASON_INVALID_RECIPIENT
        logger.exception("Twilio returned an error sending to %s", to_number)
        return False, REASON_FAILED
    except httpx.TransportError:
        logger.exception("Twilio unreachable sending to %s", to_number)
        return False, REASON_UNREACHABLE
    except Exception:
        # Retries (see app/utils/retry.py) are already exhausted - degrade
        # gracefully rather than crashing the whole alert evaluation batch.
        logger.exception("Failed to send SMS after retries")
        return False, REASON_FAILED

    logger.info("Sent SMS to %s", to_number)
    return True, REASON_SENT


def send_sms(to_number: str | None, text: str) -> bool:
    """See `send_sms_with_reason` for *why* a False came back."""
    sent, _reason = send_sms_with_reason(to_number, text)
    return sent
