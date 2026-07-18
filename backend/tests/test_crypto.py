"""Unit tests for the cloud-credentials encryption utility (app/utils/crypto.py)."""
import pytest

from app.utils.crypto import decrypt_credentials, encrypt_credentials
from app.utils.exceptions import ValidationAppError


def test_encrypt_then_decrypt_round_trips():
    original = {"access_key_id": "AKIA_FAKE", "secret_access_key": "s3cr3t"}
    token = encrypt_credentials(original)
    assert token != original
    assert decrypt_credentials(token) == original


def test_encrypted_token_does_not_contain_plaintext_secret():
    token = encrypt_credentials({"secret_access_key": "very-obvious-plaintext-marker"})
    assert "very-obvious-plaintext-marker" not in token


def test_decrypt_rejects_a_malformed_token():
    with pytest.raises(ValidationAppError):
        decrypt_credentials("not-a-real-fernet-token")
