"""Authentication endpoints: register, login, refresh, and current-user profile."""
from fastapi import APIRouter, Depends, Request
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
from app.schemas.user import UserCreate, UserProfileUpdate, UserRead

settings = get_settings()

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=201,
    summary="Register a new user account",
    responses={409: {"model": ErrorResponse, "description": "Username or email already exists"}},
)
@limiter.limit(settings.RATE_LIMIT_REGISTER)
def register(request: Request, payload: UserCreate, db: Session = Depends(get_db)) -> UserRead:
    return AuthController(db).register(payload)


@router.post(
    "/login",
    response_model=Token,
    summary="Exchange username/password for an access + refresh token pair",
    responses={401: {"model": ErrorResponse, "description": "Invalid credentials"}},
)
@limiter.limit(settings.RATE_LIMIT_LOGIN)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    return AuthController(db).login(form_data.username, form_data.password)


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
