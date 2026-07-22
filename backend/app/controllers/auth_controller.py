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
from app.schemas.user import UserCreate, UserProfileUpdate, UserRead
from app.services.auth_service import AuthService


class AuthController:
    def __init__(self, db: Session):
        self.service = AuthService(db)

    def register(self, payload: UserCreate) -> UserRead:
        user = self.service.register(payload)
        return UserRead.model_validate(user)

    def login(self, username: str, password: str) -> Token:
        return self.service.login(username, password)

    def update_profile(self, current_user: User, payload: UserProfileUpdate) -> UserRead:
        user = self.service.update_profile(current_user, payload)
        return UserRead.model_validate(user)

    def refresh(self, refresh_token: str) -> Token:
        return self.service.refresh(refresh_token)
