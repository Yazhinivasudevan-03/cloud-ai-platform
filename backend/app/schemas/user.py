"""Pydantic schemas for the User resource: request bodies and response models."""
import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.schemas.role import RoleRead

_USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{3,50}$")
# E.164: optional leading +, 1-15 digits total, first digit non-zero - the
# format Twilio (and the SMS notification channel, Phase 19) requires.
_E164_PATTERN = re.compile(r"^\+?[1-9]\d{1,14}$")


def _validate_password_strength(value: str) -> str:
    """Shared by UserCreate.password and PasswordResetConfirm.new_password
    - a reset password must meet exactly the same strength bar as a
    freshly-registered one."""
    if not re.search(r"[A-Z]", value):
        raise ValueError("password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", value):
        raise ValueError("password must contain at least one lowercase letter")
    if not re.search(r"\d", value):
        raise ValueError("password must contain at least one digit")
    return value


class UserBase(BaseModel):
    # Optional (Phase 24): the SaaS signup form has no username field at
    # all - AuthService.register() auto-derives one from the email's local
    # part when omitted. Still accepted explicitly for backward
    # compatibility with existing callers (scripts, the original API
    # contract) that pass it themselves.
    username: str | None = Field(default=None, min_length=3, max_length=50)
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=120)
    # Signup fields (Phase 24) - all optional at the schema level so the
    # pre-existing minimal {username, email, password} payload (used
    # throughout the test suite and any existing integration) keeps
    # working unchanged; the new signup form is what actually enforces
    # these as required, client-side.
    first_name: str | None = Field(default=None, max_length=60)
    last_name: str | None = Field(default=None, max_length=60)
    company_name: str | None = Field(default=None, max_length=150)
    country: str | None = Field(default=None, max_length=60)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str | None) -> str | None:
        if value is not None and not _USERNAME_PATTERN.match(value):
            raise ValueError(
                "username may only contain letters, numbers, dots, underscores and hyphens"
            )
        return value


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)
    # Optional so old-style callers that never sent it still validate;
    # when present it must match `password` (the signup form always
    # sends both).
    confirm_password: str | None = Field(default=None, min_length=8, max_length=128)
    # The signup form's "Mobile Number" field - stored on User.phone_number,
    # which already doubles as the SMS notification channel's contact
    # field (Phase 19), not a separate column.
    mobile_number: str | None = Field(default=None, max_length=20)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        return _validate_password_strength(value)

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile_number(cls, value: str | None) -> str | None:
        if value is not None and not _E164_PATTERN.match(value):
            raise ValueError("mobile_number must be in E.164 format, e.g. +14155552671")
        return value

    @model_validator(mode="after")
    def validate_confirm_password(self) -> "UserCreate":
        if self.confirm_password is not None and self.confirm_password != self.password:
            raise ValueError("password and confirm_password must match")
        return self


class UserLogin(BaseModel):
    username: str
    password: str


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # Always populated on a real record (auto-generated at registration if
    # not supplied) - narrower than UserBase's input-side `str | None`.
    username: str
    is_active: bool
    is_superuser: bool
    email_verified: bool
    phone_number: str | None = None
    roles: list[RoleRead] = []


class UserRegisterResponse(UserRead):
    """Identical to UserRead, plus a one-time email-verification token/link.

    Real SMTP delivery for verification emails isn't wired up yet (the
    user chose "log the link for now" for this environment) - so, exactly
    like the notification system's honest reason-coding, this never
    pretends an email was sent. The link is always logged server-side
    too; it's also returned here so a real dev/test workflow (including
    this project's own test suite) can complete the flow without grepping
    logs.
    """

    verification_token: str
    verification_link: str


class EmailVerificationResult(BaseModel):
    email_verified: bool
    message: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class MessageResponse(BaseModel):
    message: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, value: str) -> str:
        return _validate_password_strength(value)

    @model_validator(mode="after")
    def validate_passwords_match(self) -> "PasswordResetConfirm":
        if self.new_password != self.confirm_new_password:
            raise ValueError("new_password and confirm_new_password must match")
        return self


class UserProfileUpdate(BaseModel):
    """Self-service profile fields a user may update about themselves -
    deliberately not username/email/roles, which stay admin-managed."""

    full_name: str | None = Field(default=None, max_length=120)
    phone_number: str | None = Field(default=None, max_length=20)
    # Profile page fields (Phase 24) - same columns the signup form already
    # writes at registration; extended here so a user can also edit them
    # afterwards from their own profile.
    first_name: str | None = Field(default=None, max_length=60)
    last_name: str | None = Field(default=None, max_length=60)
    company_name: str | None = Field(default=None, max_length=150)
    country: str | None = Field(default=None, max_length=60)

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str | None) -> str | None:
        if value is not None and not _E164_PATTERN.match(value):
            raise ValueError(
                "phone_number must be in E.164 format, e.g. +14155552671"
            )
        return value


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, value: str) -> str:
        return _validate_password_strength(value)

    @model_validator(mode="after")
    def validate_passwords_match(self) -> "ChangePasswordRequest":
        if self.new_password != self.confirm_new_password:
            raise ValueError("new_password and confirm_new_password must match")
        return self
