"""Password hashing and verification using bcrypt.

bcrypt is used directly (rather than via passlib) to avoid the well-known
passlib/bcrypt>=4.1 compatibility warning, while still giving us a battle
tested, adaptive, salted hashing algorithm suitable for storing credentials.
"""
import bcrypt

_BCRYPT_ROUNDS = 12


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password, returning a UTF-8 string safe to store in the DB."""
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a plaintext password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        # Malformed hash (e.g. legacy/corrupt data) - treat as non-matching.
        return False
