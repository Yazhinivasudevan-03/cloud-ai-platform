"""Symmetric encryption for at-rest secrets that must later be decrypted (e.g.
cloud provider account credentials) - distinct from password hashing, which
is one-way and lives in app.authentication.password_handler.

Fernet requires a 32-byte urlsafe-base64-encoded key, which is an awkward
thing to ask an operator to hand-generate and store alongside every other
plain-string setting in this project. Instead, `CLOUD_CREDENTIALS_ENCRYPTION_KEY`
is an arbitrary string, like every other secret setting, and is deterministically
stretched into a valid Fernet key via SHA-256 - the same "arbitrary secret in,
fixed-size key out" pattern used for the JWT signing key, just with a
different destination format.
"""
import base64
import hashlib
import json
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config.settings import get_settings
from app.utils.exceptions import ValidationAppError


def _derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache
def _get_fernet() -> Fernet:
    settings = get_settings()
    return Fernet(_derive_fernet_key(settings.CLOUD_CREDENTIALS_ENCRYPTION_KEY))


def encrypt_credentials(credentials: dict[str, str]) -> str:
    """Serialize a credentials dict to JSON, then encrypt it. Returns a token
    string safe to store in a TEXT column."""
    payload = json.dumps(credentials, sort_keys=True).encode("utf-8")
    return _get_fernet().encrypt(payload).decode("utf-8")


def decrypt_credentials(token: str) -> dict[str, str]:
    """Inverse of `encrypt_credentials`. Raises ValidationAppError (not a raw
    cryptography exception) if the token is malformed or was encrypted under
    a different key - e.g. after CLOUD_CREDENTIALS_ENCRYPTION_KEY was rotated
    without re-encrypting existing rows."""
    try:
        payload = _get_fernet().decrypt(token.encode("utf-8"))
    except InvalidToken as exc:
        raise ValidationAppError(
            "Stored credentials could not be decrypted - the encryption key may have changed",
            code="CREDENTIALS_DECRYPT_FAILED",
        ) from exc
    return json.loads(payload.decode("utf-8"))
