"""Data-access layer for the Notification entity."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.notification import Notification
from app.repositories.base_repository import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    def __init__(self, db: Session):
        super().__init__(db, Notification)

    def search(
        self, user_id: int, is_read: bool | None, offset: int, limit: int
    ) -> tuple[list[Notification], int]:
        stmt = select(Notification).where(Notification.user_id == user_id)
        count_stmt = (
            select(func.count()).select_from(Notification).where(Notification.user_id == user_id)
        )

        if is_read is not None:
            condition = Notification.is_read == is_read
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        stmt = stmt.order_by(Notification.created_at.desc()).offset(offset).limit(limit)

        items = list(self.db.scalars(stmt).all())
        total = self.db.scalar(count_stmt) or 0
        return items, total

    def count_unread_dashboard(self, user_id: int) -> int:
        """Phase 23: the Notification Bell's badge count - one per alert
        actually delivered to this user's inbox (the "dashboard" channel
        row), not inflated by the same alert's email/SMS/Telegram/Slack/
        Teams copies, which also get their own Notification row today."""
        stmt = select(func.count()).select_from(Notification).where(
            Notification.user_id == user_id,
            Notification.is_read.is_(False),
            Notification.channel == "dashboard",
        )
        return self.db.scalar(stmt) or 0

    def count_unread_by_severity(self, user_id: int) -> dict[str, int]:
        stmt = (
            select(Alert.severity, func.count())
            .select_from(Notification)
            .join(Alert, Alert.id == Notification.alert_id)
            .where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
                Notification.channel == "dashboard",
            )
            .group_by(Alert.severity)
        )
        return dict(self.db.execute(stmt).all())
