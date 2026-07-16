"""User management endpoints, demonstrating pagination and role-based access control."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.authentication.dependencies import require_roles
from app.controllers.user_controller import UserController
from app.database.session import get_db
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.role import RoleAssignment
from app.schemas.user import UserRead

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "",
    response_model=PaginatedResponse[UserRead],
    summary="List users (admin only, paginated)",
    dependencies=[Depends(require_roles("admin"))],
)
def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PaginatedResponse[UserRead]:
    return UserController(db).list_users(page=page, page_size=page_size)


@router.get(
    "/{user_id}",
    response_model=UserRead,
    summary="Get a single user by ID (admin only)",
    dependencies=[Depends(require_roles("admin"))],
    responses={404: {"model": ErrorResponse, "description": "User not found"}},
)
def get_user(user_id: int, db: Session = Depends(get_db)) -> UserRead:
    return UserController(db).get_by_id(user_id)


@router.post(
    "/{user_id}/roles",
    response_model=UserRead,
    summary="Grant a role to a user (admin only)",
    dependencies=[Depends(require_roles("admin"))],
    responses={404: {"model": ErrorResponse, "description": "User or role not found"}},
)
def assign_role(
    user_id: int, payload: RoleAssignment, db: Session = Depends(get_db)
) -> UserRead:
    return UserController(db).assign_role(user_id, payload.role_name)


@router.delete(
    "/{user_id}/roles/{role_name}",
    response_model=UserRead,
    summary="Revoke a role from a user (admin only)",
    dependencies=[Depends(require_roles("admin"))],
    responses={404: {"model": ErrorResponse, "description": "User or role not found"}},
)
def remove_role(user_id: int, role_name: str, db: Session = Depends(get_db)) -> UserRead:
    return UserController(db).remove_role(user_id, role_name)
