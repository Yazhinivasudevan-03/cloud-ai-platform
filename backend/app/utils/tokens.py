"""Secure single-use tokens for email verification / password reset (Phase 24).

The raw token is only ever returned once, at generation time (to be
emailed - or, when SMTP isn't configured, logged - to the user); only its
SHA-256 hash is stored, mirroring why passwords are bcrypt-hashed rather
than kept in plaintext, even though this is a high-entropy random opaque
value rather than a low-entropy user-chosen secret (a fast hash is
appropriate here - unlike a password, there is nothing to brute-force
offline against a 32-byte random token).
"""
import hashlib
import secrets


def generate_token() -> str:
    """A URL-safe, single-use random token - unrelated to JWTs (this is
    for the one-time verification/reset link itself, not an API session)."""
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
