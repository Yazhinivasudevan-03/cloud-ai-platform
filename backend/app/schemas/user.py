"""Pydantic schemas for the User resource: request bodies and response models."""
import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.role import RoleRead

_USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{3,50}$")
# E.164: optional leading +, 1-15 digits total, first digit non-zero - the
# format Twilio (and the SMS notification channel, Phase 19) requires.
_E164_PATTERN = re.compile(r"^\+?[1-9]\d{1,14}$")


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=120)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if not _USERNAME_PATTERN.match(value):
            raise ValueError(
                "username may only contain letters, numbers, dots, underscores and hyphens"
            )
        return value


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if not re.search(r"[A-Z]", value):
            raise ValueError("password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", value):
            raise ValueError("password must contain at least one lowercase letter")
        if not re.search(r"\d", value):
            raise ValueError("password must contain at least one digit")
        return value


class UserLogin(BaseModel):
    username: str
    password: str


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    is_superuser: bool
    phone_number: str | None = None
    roles: list[RoleRead] = []


class UserProfileUpdate(BaseModel):
    """Self-service profile fields a user may update about themselves -
    deliberately not username/email/roles, which stay admin-managed."""

    full_name: str | None = Field(default=None, max_length=120)
    phone_number: str | None = Field(default=None, max_length=20)

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str | None) -> str | None:
        if value is not None and not _E164_PATTERN.match(value):
            raise ValueError(
                "phone_number must be in E.164 format, e.g. +14155552671"
            )
        return value
