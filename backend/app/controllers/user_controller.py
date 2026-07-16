"""Controller layer for user-management endpoints."""
import math

from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.schemas.common import PaginatedResponse, PaginationMeta
from app.schemas.user import UserRead
from app.utils.exceptions import NotFoundError


class UserController:
    def __init__(self, db: Session):
        self.db = db
        self.repository = UserRepository(db)
        self.role_repository = RoleRepository(db)

    def get_me(self, current_user: User) -> UserRead:
        return UserRead.model_validate(current_user)

    def get_by_id(self, user_id: int) -> UserRead:
        user = self.repository.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found", code="USER_NOT_FOUND")
        return UserRead.model_validate(user)

    def list_users(self, page: int, page_size: int) -> PaginatedResponse[UserRead]:
        offset = (page - 1) * page_size
        users = self.repository.list(offset=offset, limit=page_size)
        total = self.repository.count()
        total_pages = math.ceil(total / page_size) if page_size else 0
        return PaginatedResponse[UserRead](
            items=[UserRead.model_validate(u) for u in users],
            meta=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=total_pages
            ),
        )

    def assign_role(self, user_id: int, role_name: str) -> UserRead:
        user = self.repository.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found", code="USER_NOT_FOUND")
        role = self.role_repository.get_by_name(role_name)
        if role is None:
            raise NotFoundError(f"Role '{role_name}' not found", code="ROLE_NOT_FOUND")
        if role not in user.roles:
            user.roles.append(role)
            self.db.commit()
            self.db.refresh(user)
        return UserRead.model_validate(user)

    def remove_role(self, user_id: int, role_name: str) -> UserRead:
        user = self.repository.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found", code="USER_NOT_FOUND")
        role = self.role_repository.get_by_name(role_name)
        if role is None:
            raise NotFoundError(f"Role '{role_name}' not found", code="ROLE_NOT_FOUND")
        if role in user.roles:
            user.roles.remove(role)
            self.db.commit()
            self.db.refresh(user)
        return UserRead.model_validate(user)
