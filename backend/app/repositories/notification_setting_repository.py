"""Data-access layer for the NotificationSetting entity (one row per user)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notification_setting import NotificationSetting
from app.repositories.base_repository import BaseRepository


class NotificationSettingRepository(BaseRepository[NotificationSetting]):
    def __init__(self, db: Session):
        super().__init__(db, NotificationSetting)

    def get_by_user_id(self, user_id: int) -> NotificationSetting | None:
        stmt = select(NotificationSetting).where(NotificationSetting.user_id == user_id)
        return self.db.scalars(stmt).first()

    def get_or_create(self, user_id: int) -> NotificationSetting:
        """Most users never visit the Notification Settings page, so a row
        is created lazily here (on first read, first save, or the first
        alert dispatched to them - whichever comes first) rather than at
        registration time. Its absence is a well-defined "all defaults"
        state either way; this just makes that state a real row so
        model-level column defaults (e.g. email_enabled=True) apply
        consistently everywhere a NotificationSetting is read, not only
        after a flush."""
        setting = self.get_by_user_id(user_id)
        if setting is None:
            setting = self.create(NotificationSetting(user_id=user_id))
        return setting
