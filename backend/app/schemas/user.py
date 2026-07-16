"""Pydantic schemas for the User resource: request bodies and response models."""
import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.role import RoleRead

_USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{3,50}$")


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
    roles: list[RoleRead] = []
