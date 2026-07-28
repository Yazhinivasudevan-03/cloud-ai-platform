"""JWT access/refresh token creation and decoding."""
from datetime import datetime, timedelta, timezone
from enum import StrEnum

from jose import JWTError, jwt

from app.config.settings import get_settings
from app.utils.exceptions import UnauthorizedError

settings = get_settings()


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


def _create_token(
    subject: str, expires_delta: timedelta, token_type: TokenType, extra_claims: dict | None = None
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "type": token_type.value,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(subject: str) -> str:
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return _create_token(subject, expires_delta, TokenType.ACCESS)


def create_refresh_token(subject: str, remember_me: bool = False) -> str:
    """`remember_me` extends this token's lifetime (Phase 24) and is also
    embedded as a claim, so a subsequent /auth/refresh call (see
    AuthService.refresh) can tell it should keep renewing at the longer
    duration rather than silently falling back to the short default the
    moment the token is first refreshed."""
    days = (
        settings.REMEMBER_ME_REFRESH_TOKEN_EXPIRE_DAYS
        if remember_me
        else settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    expires_delta = timedelta(days=days)
    return _create_token(subject, expires_delta, TokenType.REFRESH, extra_claims={"remember_me": remember_me})


def decode_token(token: str, expected_type: TokenType) -> dict:
    """Decode and validate a JWT, raising UnauthorizedError on any failure."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        raise UnauthorizedError("Could not validate credentials", code="INVALID_TOKEN") from exc

    if payload.get("type") != expected_type.value:
        raise UnauthorizedError("Incorrect token type", code="INVALID_TOKEN_TYPE")

    return payload
