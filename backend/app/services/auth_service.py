"""Business logic for registration, authentication and token issuance.

Services orchestrate repositories and domain rules; they contain no HTTP
concerns (no status codes, no request/response objects) so they can be
reused from routers, background jobs, or CLI scripts alike.
"""
import re
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.authentication.jwt_handler import create_access_token, create_refresh_token, decode_token
from app.authentication.jwt_handler import TokenType
from app.authentication.password_handler import hash_password, verify_password
from app.config.settings import get_settings
from app.models.audit_log import AuditLog
from app.models.user import User
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.schemas.token import Token
from app.schemas.user import UserCreate, UserProfileUpdate
from app.utils.exceptions import ConflictError, ForbiddenError, UnauthorizedError, ValidationAppError
from app.utils.logger import get_logger
from app.utils.tokens import generate_token, hash_token

DEFAULT_ROLE_NAME = "viewer"
# Same allowed character set as UserBase._USERNAME_PATTERN in app/schemas/user.py.
_USERNAME_SAFE_CHARS = re.compile(r"[^a-zA-Z0-9_.-]")

settings = get_settings()
logger = get_logger("auth")


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repository = UserRepository(db)
        self.role_repository = RoleRepository(db)

    def _generate_username_from_email(self, email: str) -> str:
        """Derive a unique username from an email's local part (Phase 24) -
        the new SaaS signup form has no username field at all. Strips
        characters the username pattern disallows (e.g. a '+' alias tag),
        pads short local parts to meet the 3-character minimum, and
        appends a numeric suffix on collision."""
        local_part = _USERNAME_SAFE_CHARS.sub("", email.split("@")[0])
        base = local_part if len(local_part) >= 3 else f"user{local_part}"
        base = base[:50]

        candidate = base
        suffix = 1
        while self.user_repository.get_by_username(candidate) is not None:
            suffix += 1
            candidate = f"{base}{suffix}"[:50]
        return candidate

    def build_verification_link(self, raw_token: str) -> str:
        return f"{settings.FRONTEND_BASE_URL.rstrip('/')}/verify-email?token={raw_token}"

    def register(self, payload: UserCreate) -> tuple[User, str]:
        """Returns the new user and the raw (unhashed) email-verification
        token - the only place that raw value is ever available (only its
        hash is persisted, mirroring password hashing - see
        app/utils/tokens.py)."""
        if payload.username:
            if self.user_repository.username_or_email_exists(payload.username, payload.email):
                raise ConflictError(
                    "A user with this username or email already exists", code="USER_EXISTS"
                )
            username = payload.username
        else:
            if self.user_repository.get_by_email(payload.email) is not None:
                raise ConflictError(
                    "A user with this username or email already exists", code="USER_EXISTS"
                )
            username = self._generate_username_from_email(payload.email)

        default_role = self.role_repository.get_or_create(
            DEFAULT_ROLE_NAME, description="Read-only access to dashboards and reports"
        )

        raw_token = generate_token()
        user = User(
            username=username,
            email=payload.email,
            full_name=payload.full_name,
            first_name=payload.first_name,
            last_name=payload.last_name,
            company_name=payload.company_name,
            country=payload.country,
            phone_number=payload.mobile_number,
            hashed_password=hash_password(payload.password),
            is_active=True,
            is_superuser=False,
            email_verification_token_hash=hash_token(raw_token),
            email_verification_expires_at=datetime.utcnow()
            + timedelta(hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS),
        )
        user.roles.append(default_role)
        created = self.user_repository.create(user)

        verification_link = self.build_verification_link(raw_token)
        # Real SMTP delivery for verification emails isn't wired up yet
        # (the user's own choice: "log the link for now") - logged here,
        # same as every other not-yet-configured notification channel in
        # this project, never silently skipped.
        logger.info(
            "Email verification link for %s (log-only - SMTP delivery not yet wired "
            "up for verification emails): %s",
            created.email,
            verification_link,
        )
        return created, raw_token

    def authenticate(self, identifier: str, password: str) -> User:
        """`identifier` may be either a username or an email address (Phase
        24) - the SaaS login form only collects email, but existing
        username-based callers (and OAuth2PasswordRequestForm's `username`
        field, which the frontend now puts an email address into) keep
        working unchanged."""
        user = self.user_repository.get_by_username(identifier)
        if user is None:
            user = self.user_repository.get_by_email(identifier)
        if user is None or not verify_password(password, user.hashed_password):
            # AuditLogMiddleware's own generic row for this request has no
            # user_id (there is no authenticated "current user" for a login
            # request that hasn't succeeded yet - see app/middleware/
            # audit_middleware.py) - so the Security evaluator (Phase 23)
            # would never have a user to count failed attempts against
            # without this: a second, more precise row, written here where
            # the targeted account (if the username matched one) is
            # actually known. Committed immediately, same as the
            # middleware's own row, since this whole request is about to
            # raise and roll back otherwise.
            if user is not None:
                self.db.add(
                    AuditLog(
                        user_id=user.id,
                        action="POST /api/v1/auth/login",
                        entity_type="auth",
                        details="status=401",
                    )
                )
                self.db.commit()
            raise UnauthorizedError("Incorrect username or password", code="INVALID_CREDENTIALS")
        if not user.is_active:
            raise UnauthorizedError("User account is inactive", code="INACTIVE_USER")
        if not user.email_verified:
            raise ForbiddenError(
                "Please verify your email address before logging in", code="EMAIL_NOT_VERIFIED"
            )
        return user

    def login(self, username: str, password: str, remember_me: bool = False) -> Token:
        user = self.authenticate(username, password)
        return Token(
            access_token=create_access_token(user.username),
            refresh_token=create_refresh_token(user.username, remember_me=remember_me),
        )

    def verify_email(self, token: str) -> User:
        user = self.user_repository.get_by_email_verification_token_hash(hash_token(token))
        if user is None or user.email_verification_expires_at is None:
            raise ValidationAppError("Invalid or expired verification token", code="INVALID_OR_EXPIRED_TOKEN")
        if user.email_verification_expires_at < datetime.utcnow():
            raise ValidationAppError("Invalid or expired verification token", code="INVALID_OR_EXPIRED_TOKEN")

        user.email_verified = True
        user.email_verification_token_hash = None
        user.email_verification_expires_at = None
        self.db.commit()
        self.db.refresh(user)
        return user

    def resend_verification(self, email: str) -> str | None:
        """Issues a fresh verification token and returns its link - or
        None if there's nothing to do (unknown email, or already
        verified). Always looks and behaves the same to the caller either
        way (see AuthController/router: always a generic 200), so a
        malicious caller can't use this to discover which emails are
        registered."""
        user = self.user_repository.get_by_email(email)
        if user is None or user.email_verified:
            return None

        raw_token = generate_token()
        user.email_verification_token_hash = hash_token(raw_token)
        user.email_verification_expires_at = datetime.utcnow() + timedelta(
            hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS
        )
        self.db.commit()

        verification_link = self.build_verification_link(raw_token)
        logger.info(
            "Resent email verification link for %s (log-only): %s", user.email, verification_link
        )
        return verification_link

    def build_reset_link(self, raw_token: str) -> str:
        return f"{settings.FRONTEND_BASE_URL.rstrip('/')}/reset-password?token={raw_token}"

    def forgot_password(self, email: str) -> None:
        """Always looks the same to the caller regardless of outcome (see
        AuthController/router: always a generic 200) - unlike registration,
        an unauthenticated stranger submitting an arbitrary email here must
        never be able to tell whether that email has an account, so
        (unlike verify-email) the raw token/link is never returned over
        the API - only ever logged, per the user's "log the link for now"
        choice."""
        user = self.user_repository.get_by_email(email)
        if user is None:
            return

        raw_token = generate_token()
        user.password_reset_token_hash = hash_token(raw_token)
        user.password_reset_expires_at = datetime.utcnow() + timedelta(
            hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS
        )
        self.db.commit()

        reset_link = self.build_reset_link(raw_token)
        logger.info("Password reset link for %s (log-only): %s", user.email, reset_link)

    def reset_password(self, token: str, new_password: str) -> User:
        user = self.user_repository.get_by_password_reset_token_hash(hash_token(token))
        if user is None or user.password_reset_expires_at is None:
            raise ValidationAppError(
                "Invalid or expired password reset token", code="INVALID_OR_EXPIRED_TOKEN"
            )
        if user.password_reset_expires_at < datetime.utcnow():
            raise ValidationAppError(
                "Invalid or expired password reset token", code="INVALID_OR_EXPIRED_TOKEN"
            )

        user.hashed_password = hash_password(new_password)
        user.password_reset_token_hash = None
        user.password_reset_expires_at = None
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_profile(self, current_user: User, payload: UserProfileUpdate) -> User:
        if payload.full_name is not None:
            current_user.full_name = payload.full_name
        if payload.phone_number is not None:
            current_user.phone_number = payload.phone_number
        if payload.first_name is not None:
            current_user.first_name = payload.first_name
        if payload.last_name is not None:
            current_user.last_name = payload.last_name
        if payload.company_name is not None:
            current_user.company_name = payload.company_name
        if payload.country is not None:
            current_user.country = payload.country
        self.db.commit()
        self.db.refresh(current_user)
        return current_user

    def change_password(self, current_user: User, current_password: str, new_password: str) -> User:
        if not verify_password(current_password, current_user.hashed_password):
            raise UnauthorizedError("Current password is incorrect", code="INVALID_CURRENT_PASSWORD")
        current_user.hashed_password = hash_password(new_password)
        self.db.commit()
        self.db.refresh(current_user)
        return current_user

    def refresh(self, refresh_token: str) -> Token:
        payload = decode_token(refresh_token, TokenType.REFRESH)
        username: str = payload["sub"]
        # Carries the original login's "Remember Me" choice forward, so a
        # remembered session keeps renewing at the long duration instead
        # of quietly reverting to the short default on first refresh.
        remember_me: bool = payload.get("remember_me", False)
        user = self.user_repository.get_by_username(username)
        if user is None or not user.is_active:
            raise UnauthorizedError("User not found or inactive", code="USER_NOT_FOUND")
        return Token(
            access_token=create_access_token(user.username),
            refresh_token=create_refresh_token(user.username, remember_me=remember_me),
        )
