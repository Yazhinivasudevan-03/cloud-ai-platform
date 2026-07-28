"""Controller layer for authentication endpoints.

Controllers sit between routers (HTTP layer) and services (business logic):
they translate schema objects to/from service calls. Keeping this layer
separate from the router means the same orchestration can be reused by
multiple transport layers (REST here, potentially GraphQL/CLI later)
without duplicating logic.
"""
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.token import Token
from app.schemas.user import (
    ChangePasswordRequest,
    EmailVerificationResult,
    MessageResponse,
    PasswordResetConfirm,
    UserCreate,
    UserProfileUpdate,
    UserRead,
    UserRegisterResponse,
)
from app.services.auth_service import AuthService


class AuthController:
    def __init__(self, db: Session):
        self.service = AuthService(db)

    def register(self, payload: UserCreate) -> UserRegisterResponse:
        user, raw_token = self.service.register(payload)
        return UserRegisterResponse(
            **UserRead.model_validate(user).model_dump(),
            verification_token=raw_token,
            verification_link=self.service.build_verification_link(raw_token),
        )

    def login(self, username: str, password: str, remember_me: bool = False) -> Token:
        return self.service.login(username, password, remember_me)

    def verify_email(self, token: str) -> EmailVerificationResult:
        self.service.verify_email(token)
        return EmailVerificationResult(email_verified=True, message="Email verified successfully")

    def resend_verification(self, email: str) -> EmailVerificationResult:
        self.service.resend_verification(email)
        # Always the same generic response regardless of whether the email
        # existed/was already verified - see AuthService.resend_verification.
        return EmailVerificationResult(
            email_verified=False,
            message="If an account with that email exists and isn't verified yet, "
            "a new verification link has been sent.",
        )

    def forgot_password(self, email: str) -> MessageResponse:
        self.service.forgot_password(email)
        # Always the same generic response regardless of whether the email
        # exists - see AuthService.forgot_password.
        return MessageResponse(
            message="If an account with that email exists, a password reset link has been sent."
        )

    def reset_password(self, payload: PasswordResetConfirm) -> MessageResponse:
        self.service.reset_password(payload.token, payload.new_password)
        return MessageResponse(message="Password has been reset successfully.")

    def update_profile(self, current_user: User, payload: UserProfileUpdate) -> UserRead:
        user = self.service.update_profile(current_user, payload)
        return UserRead.model_validate(user)

    def change_password(self, current_user: User, payload: ChangePasswordRequest) -> MessageResponse:
        self.service.change_password(current_user, payload.current_password, payload.new_password)
        return MessageResponse(message="Password has been changed successfully.")

    def refresh(self, refresh_token: str) -> Token:
        return self.service.refresh(refresh_token)
