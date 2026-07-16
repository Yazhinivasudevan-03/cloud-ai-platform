"""Business logic for a user's own notifications (self-service only)."""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.repositories.notification_repository import NotificationRepository
from app.utils.exceptions import ForbiddenError, NotFoundError


class NotificationService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = NotificationRepository(db)

    def list_for_user(
        self, user_id: int, is_read: bool | None, page: int, page_size: int
    ) -> tuple[list[Notification], int]:
        offset = (page - 1) * page_size
        return self.repository.search(user_id, is_read, offset, page_size)

    def mark_read(self, notification_id: int, current_user_id: int) -> Notification:
        notification = self.repository.get_by_id(notification_id)
        if notification is None:
            raise NotFoundError(
                f"Notification {notification_id} not found", code="NOTIFICATION_NOT_FOUND"
            )
        if notification.user_id != current_user_id:
            raise ForbiddenError(
                "Cannot mark another user's notification as read", code="NOT_YOUR_NOTIFICATION"
            )
        if not notification.is_read:
            notification.is_read = True
            self.db.commit()
            self.db.refresh(notification)
        return notification
