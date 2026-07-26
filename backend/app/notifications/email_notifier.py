"""Email delivery via SMTP.

Configured entirely through environment variables (see `Settings`). When
`SMTP_HOST` is unset, `send` logs the message instead of attempting a
connection - this lets the alert pipeline run end-to-end in any environment
(including this project's own development/CI, which has no real mail server)
without every alert failing loudly, while still doing the real thing the
moment a deployer configures actual SMTP credentials.
"""
import smtplib
import socket
from email.message import EmailMessage

from app.config.settings import get_settings
from app.utils.logger import get_logger
from app.utils.retry import smtp_retry

logger = get_logger("notifications.email")

# Real, distinct failure reasons (Phase 23 follow-up) - collapsing every one
# of these into a single boolean is what made the Notification Settings
# "Send Test Notification" result say only "failed" with no way to tell
# "you haven't configured SMTP yet" apart from "your real SMTP credentials
# are wrong" or "the SMTP server is unreachable". Never fabricated - each
# reason is only ever returned when the corresponding real condition/
# exception actually occurred.
REASON_NOT_CONFIGURED = "not_configured"
REASON_SENT = "sent"
REASON_AUTH_FAILED = "auth_failed"
REASON_UNREACHABLE = "unreachable"
REASON_INVALID_RECIPIENT = "invalid_recipient"
REASON_FAILED = "failed"


@smtp_retry
def _send(settings, message: EmailMessage) -> None:
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as client:
        if settings.SMTP_USE_TLS:
            client.starttls()
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            client.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        client.send_message(message)


def send_email_with_reason(to_address: str, subject: str, body: str) -> tuple[bool, str]:
    """Send an email, returning (sent, reason). `reason` is one of the
    REASON_* constants above, always reflecting what genuinely happened -
    never a guessed/fabricated success."""
    settings = get_settings()
    if not settings.SMTP_HOST:
        logger.info("SMTP not configured; would send email to %s: %s", to_address, subject)
        return False, REASON_NOT_CONFIGURED

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.SMTP_FROM_ADDRESS or "alerts@cloud-ai-platform.local"
    message["To"] = to_address
    message.set_content(body)

    try:
        _send(settings, message)
    except smtplib.SMTPAuthenticationError:
        logger.exception("SMTP authentication failed sending to %s", to_address)
        return False, REASON_AUTH_FAILED
    except smtplib.SMTPRecipientsRefused:
        logger.exception("SMTP server refused recipient %s", to_address)
        return False, REASON_INVALID_RECIPIENT
    except (socket.gaierror, ConnectionRefusedError, TimeoutError, smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected):
        logger.exception("SMTP server unreachable sending to %s", to_address)
        return False, REASON_UNREACHABLE
    except Exception:
        # Retries (see app/utils/retry.py) are already exhausted - degrade
        # gracefully rather than crashing the whole alert evaluation batch.
        logger.exception("Failed to send email to %s after retries", to_address)
        return False, REASON_FAILED

    logger.info("Sent email to %s: %s", to_address, subject)
    return True, REASON_SENT


def send_email(to_address: str, subject: str, body: str) -> bool:
    """Send an email. Returns True if actually sent, False if only logged
    (SMTP not configured, or delivery failed even after retries) - callers
    use this to decide whether to record the notification as delivered.
    See `send_email_with_reason` for *why* a False came back."""
    sent, _reason = send_email_with_reason(to_address, subject, body)
    return sent
