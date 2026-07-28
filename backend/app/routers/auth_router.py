"""Authentication endpoints: register, login, refresh, and current-user profile."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.authentication.dependencies import get_current_active_user
from app.config.settings import get_settings
from app.controllers.auth_controller import AuthController
from app.database.session import get_db
from app.middleware.rate_limiter import limiter
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.token import Token
from app.schemas.user import (
    ChangePasswordRequest,
    EmailVerificationResult,
    ForgotPasswordRequest,
    MessageResponse,
    PasswordResetConfirm,
    ResendVerificationRequest,
    UserCreate,
    UserProfileUpdate,
    UserRead,
    UserRegisterResponse,
)

settings = get_settings()

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserRegisterResponse,
    status_code=201,
    summary="Register a new user account",
    responses={409: {"model": ErrorResponse, "description": "Username or email already exists"}},
)
@limiter.limit(settings.RATE_LIMIT_REGISTER)
def register(request: Request, payload: UserCreate, db: Session = Depends(get_db)) -> UserRegisterResponse:
    return AuthController(db).register(payload)


@router.get(
    "/verify-email",
    response_model=EmailVerificationResult,
    summary="Verify a user's email address using the token from their verification link",
    responses={422: {"model": ErrorResponse, "description": "Invalid or expired token"}},
)
def verify_email(token: str, db: Session = Depends(get_db)) -> EmailVerificationResult:
    return AuthController(db).verify_email(token)


@router.post(
    "/resend-verification",
    response_model=EmailVerificationResult,
    summary="Resend the email verification link (always a generic response, "
    "regardless of whether the email exists, to avoid account enumeration)",
)
@limiter.limit(settings.RATE_LIMIT_REGISTER)
def resend_verification(
    request: Request, payload: ResendVerificationRequest, db: Session = Depends(get_db)
) -> EmailVerificationResult:
    return AuthController(db).resend_verification(payload.email)


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    summary="Request a password reset link (always a generic response, "
    "regardless of whether the email exists, to avoid account enumeration)",
)
@limiter.limit(settings.RATE_LIMIT_REGISTER)
def forgot_password(
    request: Request, payload: ForgotPasswordRequest, db: Session = Depends(get_db)
) -> MessageResponse:
    return AuthController(db).forgot_password(payload.email)


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Reset a password using the token from a forgot-password link",
    responses={422: {"model": ErrorResponse, "description": "Invalid or expired token"}},
)
@limiter.limit(settings.RATE_LIMIT_LOGIN)
def reset_password(
    request: Request, payload: PasswordResetConfirm, db: Session = Depends(get_db)
) -> MessageResponse:
    return AuthController(db).reset_password(payload)


@router.post(
    "/login",
    response_model=Token,
    summary="Exchange username/password for an access + refresh token pair. "
    "Set remember_me=true for a long-lived refresh token (30 days vs the "
    "default 7).",
    responses={401: {"model": ErrorResponse, "description": "Invalid credentials"}},
)
@limiter.limit(settings.RATE_LIMIT_LOGIN)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    remember_me: bool = Form(False),
    db: Session = Depends(get_db),
) -> Token:
    return AuthController(db).login(form_data.username, form_data.password, remember_me)


@router.post(
    "/refresh",
    response_model=Token,
    summary="Exchange a valid refresh token for a new token pair",
    responses={401: {"model": ErrorResponse, "description": "Invalid or expired refresh token"}},
)
@limiter.limit(settings.RATE_LIMIT_REFRESH)
def refresh(request: Request, refresh_token: str, db: Session = Depends(get_db)) -> Token:
    return AuthController(db).refresh(refresh_token)


@router.get(
    "/me",
    response_model=UserRead,
    summary="Return the profile of the currently authenticated user",
)
def me(current_user: User = Depends(get_current_active_user)) -> UserRead:
    return UserRead.model_validate(current_user)


@router.patch(
    "/me",
    response_model=UserRead,
    summary="Update the currently authenticated user's own profile "
    "(full_name, phone_number - the latter enables the SMS notification channel)",
)
def update_me(
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> UserRead:
    return AuthController(db).update_profile(current_user, payload)


@router.post(
    "/change-password",
    response_model=MessageResponse,
    summary="Change the currently authenticated user's own password",
    responses={401: {"model": ErrorResponse, "description": "Current password is incorrect"}},
)
@limiter.limit(settings.RATE_LIMIT_LOGIN)
def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> MessageResponse:
    return AuthController(db).change_password(current_user, payload)
