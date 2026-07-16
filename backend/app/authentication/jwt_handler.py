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


def _create_token(subject: str, expires_delta: timedelta, token_type: TokenType) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "type": token_type.value,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(subject: str) -> str:
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return _create_token(subject, expires_delta, TokenType.ACCESS)


def create_refresh_token(subject: str) -> str:
    expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return _create_token(subject, expires_delta, TokenType.REFRESH)


def decode_token(token: str, expected_type: TokenType) -> dict:
    """Decode and validate a JWT, raising UnauthorizedError on any failure."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        raise UnauthorizedError("Could not validate credentials", code="INVALID_TOKEN") from exc

    if payload.get("type") != expected_type.value:
        raise UnauthorizedError("Incorrect token type", code="INVALID_TOKEN_TYPE")

    return payload
