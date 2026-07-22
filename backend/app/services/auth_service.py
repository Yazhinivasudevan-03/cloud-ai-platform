"""Business logic for registration, authentication and token issuance.

Services orchestrate repositories and domain rules; they contain no HTTP
concerns (no status codes, no request/response objects) so they can be
reused from routers, background jobs, or CLI scripts alike.
"""
from sqlalchemy.orm import Session

from app.authentication.jwt_handler import create_access_token, create_refresh_token, decode_token
from app.authentication.jwt_handler import TokenType
from app.authentication.password_handler import hash_password, verify_password
from app.models.user import User
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.schemas.token import Token
from app.schemas.user import UserCreate, UserProfileUpdate
from app.utils.exceptions import ConflictError, UnauthorizedError

DEFAULT_ROLE_NAME = "viewer"


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repository = UserRepository(db)
        self.role_repository = RoleRepository(db)

    def register(self, payload: UserCreate) -> User:
        if self.user_repository.username_or_email_exists(payload.username, payload.email):
            raise ConflictError(
                "A user with this username or email already exists", code="USER_EXISTS"
            )

        default_role = self.role_repository.get_or_create(
            DEFAULT_ROLE_NAME, description="Read-only access to dashboards and reports"
        )

        user = User(
            username=payload.username,
            email=payload.email,
            full_name=payload.full_name,
            hashed_password=hash_password(payload.password),
            is_active=True,
            is_superuser=False,
        )
        user.roles.append(default_role)
        return self.user_repository.create(user)

    def authenticate(self, username: str, password: str) -> User:
        user = self.user_repository.get_by_username(username)
        if user is None or not verify_password(password, user.hashed_password):
            raise UnauthorizedError("Incorrect username or password", code="INVALID_CREDENTIALS")
        if not user.is_active:
            raise UnauthorizedError("User account is inactive", code="INACTIVE_USER")
        return user

    def login(self, username: str, password: str) -> Token:
        user = self.authenticate(username, password)
        return Token(
            access_token=create_access_token(user.username),
            refresh_token=create_refresh_token(user.username),
        )

    def update_profile(self, current_user: User, payload: UserProfileUpdate) -> User:
        if payload.full_name is not None:
            current_user.full_name = payload.full_name
        if payload.phone_number is not None:
            current_user.phone_number = payload.phone_number
        self.db.commit()
        self.db.refresh(current_user)
        return current_user

    def refresh(self, refresh_token: str) -> Token:
        payload = decode_token(refresh_token, TokenType.REFRESH)
        username: str = payload["sub"]
        user = self.user_repository.get_by_username(username)
        if user is None or not user.is_active:
            raise UnauthorizedError("User not found or inactive", code="USER_NOT_FOUND")
        return Token(
            access_token=create_access_token(user.username),
            refresh_token=create_refresh_token(user.username),
        )
