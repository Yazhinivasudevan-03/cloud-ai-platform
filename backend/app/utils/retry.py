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
import requests
import tenacity
from twilio.base.exceptions import TwilioRestException


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


def _is_retryable_twilio_error(exc: BaseException) -> bool:
    if isinstance(exc, TwilioRestException):
        # A real Twilio error response - only a 5xx (Twilio's own outage) is
        # worth retrying; 4xx means the request itself is wrong (bad
        # credentials, bad phone number) and retrying it 3 times only
        # wastes time before failing the same way.
        return exc.status >= 500
    # The Twilio SDK's default HTTP client is `requests` and lets
    # connection-level failures (DNS failure, connection refused, timeout)
    # propagate as real `requests` exceptions rather than wrapping them -
    # confirmed empirically against the installed `twilio` package, not
    # assumed.
    return isinstance(exc, requests.exceptions.RequestException)


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

twilio_retry = tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable_twilio_error),
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
