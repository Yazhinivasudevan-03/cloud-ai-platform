"""FastAPI dependencies for authentication and role-based access control (RBAC)."""
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.authentication.jwt_handler import TokenType, decode_token
from app.config.settings import get_settings
from app.database.session import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.utils.exceptions import ForbiddenError, UnauthorizedError

settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    """Resolve the authenticated User from a Bearer access token."""
    payload = decode_token(token, TokenType.ACCESS)
    username: str | None = payload.get("sub")
    if username is None:
        raise UnauthorizedError("Could not validate credentials", code="INVALID_TOKEN")

    user = UserRepository(db).get_by_username(username)
    if user is None:
        raise UnauthorizedError("User not found", code="USER_NOT_FOUND")
    return user


def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Ensure the authenticated user's account has not been deactivated."""
    if not current_user.is_active:
        raise ForbiddenError("User account is inactive", code="INACTIVE_USER")
    return current_user


def require_roles(*allowed_roles: str):
    """Dependency factory enforcing that the current user holds at least one
    of the given roles. Superusers always pass. Usage:

        @router.get("/admin-only", dependencies=[Depends(require_roles("admin"))])
    """

    def _checker(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.is_superuser:
            return current_user
        user_role_names = {role.name for role in current_user.roles}
        if not user_role_names.intersection(allowed_roles):
            raise ForbiddenError(
                f"Requires one of roles: {', '.join(allowed_roles)}", code="INSUFFICIENT_ROLE"
            )
        return current_user

    return _checker
