"""Shared tenacity retry helpers for outbound calls to external services -
a few attempts with short exponential backoff for genuinely transient
failures, so a single blip in an external dependency (SMTP server, a
webhook) doesn't fail an entire alert/notification batch run. Each helper
only retries failure modes actually worth retrying - a permanent config
error (bad webhook URL, bad credentials) retried 3 times just wastes time
before failing anyway, so those are deliberately excluded.
"""
import smtplib

import httpx
import tenacity


def _is_retryable_http_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


def _is_retryable_smtp_error(exc: BaseException) -> bool:
    if isinstance(exc, (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused)):
        return False  # permanent config/input errors, not transient
    return isinstance(exc, (smtplib.SMTPException, OSError))


http_retry = tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable_http_error),
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)

smtp_retry = tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable_smtp_error),
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
