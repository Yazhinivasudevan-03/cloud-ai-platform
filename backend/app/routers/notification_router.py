"""Self-service notification endpoints: every user reads and manages only
their own notifications."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.authentication.dependencies import get_current_active_user
from app.controllers.notification_controller import NotificationController
from app.database.session import get_db
from app.models.user import User
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.notification import NotificationRead

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get(
    "",
    response_model=PaginatedResponse[NotificationRead],
    summary="List the current user's own notifications (paginated, filterable by read status)",
)
def list_my_notifications(
    is_read: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PaginatedResponse[NotificationRead]:
    return NotificationController(db).list_for_user(current_user.id, is_read, page, page_size)


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationRead,
    summary="Mark one of the current user's own notifications as read",
    responses={
        403: {"model": ErrorResponse, "description": "Not this user's notification"},
        404: {"model": ErrorResponse, "description": "Notification not found"},
    },
)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> NotificationRead:
    return NotificationController(db).mark_read(notification_id, current_user.id)
