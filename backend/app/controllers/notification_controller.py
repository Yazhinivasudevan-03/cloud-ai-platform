"""Controller layer for a user's own Notification endpoints."""
import math

from sqlalchemy.orm import Session

from app.schemas.common import PaginatedResponse, PaginationMeta
from app.schemas.notification import NotificationRead
from app.services.notification_service import NotificationService


class NotificationController:
    def __init__(self, db: Session):
        self.service = NotificationService(db)

    def list_for_user(
        self, user_id: int, is_read: bool | None, page: int, page_size: int
    ) -> PaginatedResponse[NotificationRead]:
        items, total = self.service.list_for_user(user_id, is_read, page, page_size)
        total_pages = math.ceil(total / page_size) if page_size else 0
        return PaginatedResponse[NotificationRead](
            items=[NotificationRead.model_validate(i) for i in items],
            meta=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=total_pages
            ),
        )

    def mark_read(self, notification_id: int, current_user_id: int) -> NotificationRead:
        return NotificationRead.model_validate(
            self.service.mark_read(notification_id, current_user_id)
        )
