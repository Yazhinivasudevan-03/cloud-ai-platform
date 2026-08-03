"""SMS delivery via the official Twilio Python SDK (`twilio.rest.Client`),
the Messages resource's `.create()` call.

Every other notifier in this project (`slack_notifier.py`/
`telegram_notifier.py`/`email_notifier.py`) is a thin `httpx`/`smtplib` call
directly against the provider's own plain REST/SMTP interface rather than an
SDK, since there's normally no real advantage to the extra dependency for a
single authenticated POST. SMS is the deliberate exception: the official
Twilio SDK is what was specifically requested for this integration, and it
also gives real, structured error detail (`TwilioRestException`'s
`.status`/`.code`/`.msg`) that a hand-rolled REST call would otherwise have
to reconstruct by hand.

Reads TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN/TWILIO_PHONE_NUMBER from
Settings (backed by real environment variables / .env - see
app/config/settings.py) - never hardcoded. When any of the three is unset,
or the target user has no `phone_number` on file, `send_sms` logs instead
of calling the API - see `email_notifier.py` for why that fallback exists.
"""
from typing import NamedTuple

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.config.settings import get_settings
from app.utils.logger import get_logger
from app.utils.retry import twilio_retry

logger = get_logger("notifications.sms")

REASON_NOT_CONFIGURED = "not_configured"
REASON_NO_RECIPIENT = "no_recipient"
REASON_SENT = "sent"
REASON_AUTH_FAILED = "auth_failed"
REASON_UNREACHABLE = "unreachable"
REASON_INVALID_RECIPIENT = "invalid_recipient"
REASON_FAILED = "failed"


class SmsSendResult(NamedTuple):
    """`reason` keeps send_sms_with_reason's existing, backward-compatible
    contract exactly (REASON_SENT on success, a REASON_* bucket or real
    Twilio error detail on failure) - `status` separately carries Twilio's
    own real message status ("queued", etc.) on success only, for callers
    (Notification History) that want that finer detail without changing
    what `reason` has always meant."""

    sent: bool
    reason: str
    message_sid: str | None = None
    status: str | None = None


@twilio_retry
def _create_message(account_sid: str, auth_token: str, from_number: str, to_number: str, body: str):
    client = Client(account_sid, auth_token)
    return client.messages.create(to=to_number, from_=from_number, body=body)


def send_sms_with_details(to_number: str | None, text: str) -> SmsSendResult:
    """Send a real SMS via the Twilio API, returning (sent, reason,
    message_sid).

    On success, `reason` is the real Twilio message status at send time
    (e.g. "queued") and `message_sid` is the real Twilio Message SID -
    both logged, and both meant to be persisted verbatim onto a
    Notification row (see dispatcher.py) for Notification History. On
    failure, `reason` is one of the REASON_* buckets above for the common,
    genuinely-distinguishable cases (auth rejected, unreachable, invalid
    recipient) - for anything else, `reason` carries Twilio's own real
    error code and message verbatim (f"failed: Twilio error {code} -
    {message}"), never a generic "it failed", and `message_sid` is None.
    Every Twilio API response (success or failure) is logged.
    """
    settings = get_settings()
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_PHONE_NUMBER:
        logger.info("Twilio not configured; would send SMS to %s: %s", to_number, text)
        return SmsSendResult(False, REASON_NOT_CONFIGURED)
    if not to_number:
        logger.info("User has no phone_number on file; would send SMS: %s", text)
        return SmsSendResult(False, REASON_NO_RECIPIENT)

    try:
        message = _create_message(
            settings.TWILIO_ACCOUNT_SID,
            settings.TWILIO_AUTH_TOKEN,
            settings.TWILIO_PHONE_NUMBER,
            to_number,
            text,
        )
    except TwilioRestException as exc:
        logger.error(
            "Twilio rejected the SMS to %s (status=%s code=%s uri=%s): %s",
            to_number, exc.status, exc.code, exc.uri, exc.msg,
        )
        if exc.status in (401, 403):
            return SmsSendResult(False, REASON_AUTH_FAILED)
        if exc.status == 400:
            return SmsSendResult(False, REASON_INVALID_RECIPIENT)
        return SmsSendResult(False, f"{REASON_FAILED}: Twilio error {exc.code} - {exc.msg}")
    except Exception as exc:
        # Retries (see app/utils/retry.py) are already exhausted for
        # anything transient - degrade gracefully rather than crashing the
        # whole alert evaluation batch, but keep the real exception detail
        # rather than a bare "failed".
        logger.exception("Could not reach Twilio sending SMS to %s", to_number)
        return SmsSendResult(False, f"{REASON_UNREACHABLE}: {exc}")

    logger.info(
        "Twilio accepted SMS to %s: sid=%s status=%s error_code=%s error_message=%s",
        to_number, message.sid, message.status, message.error_code, message.error_message,
    )
    return SmsSendResult(True, REASON_SENT, message.sid, message.status)


def send_sms_with_reason(to_number: str | None, text: str) -> tuple[bool, str]:
    """See `send_sms_with_details` - this is that same call, minus the
    message SID, for existing callers that only need (sent, reason)."""
    result = send_sms_with_details(to_number, text)
    return result.sent, result.reason


def send_sms(to_number: str | None, text: str) -> bool:
    """See `send_sms_with_reason` for *why* a False came back."""
    return send_sms_with_details(to_number, text).sent
