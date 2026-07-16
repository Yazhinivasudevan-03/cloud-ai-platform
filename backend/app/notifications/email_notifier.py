"""Email delivery via SMTP.

Configured entirely through environment variables (see `Settings`). When
`SMTP_HOST` is unset, `send` logs the message instead of attempting a
connection - this lets the alert pipeline run end-to-end in any environment
(including this project's own development/CI, which has no real mail server)
without every alert failing loudly, while still doing the real thing the
moment a deployer configures actual SMTP credentials.
"""
import smtplib
from email.message import EmailMessage

from app.config.settings import get_settings
from app.utils.logger import get_logger

logger = get_logger("notifications.email")


def send_email(to_address: str, subject: str, body: str) -> bool:
    """Send an email. Returns True if actually sent, False if only logged
    (SMTP not configured) - callers use this to decide whether to record the
    notification as delivered.
    """
    settings = get_settings()
    if not settings.SMTP_HOST:
        logger.info("SMTP not configured; would send email to %s: %s", to_address, subject)
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.SMTP_FROM_ADDRESS or "alerts@cloud-ai-platform.local"
    message["To"] = to_address
    message.set_content(body)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as client:
        if settings.SMTP_USE_TLS:
            client.starttls()
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            client.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        client.send_message(message)

    logger.info("Sent email to %s: %s", to_address, subject)
    return True
