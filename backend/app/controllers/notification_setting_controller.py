"""Controller layer for the self-service notification settings endpoints."""
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.notification_setting import (
    NotificationSettingRead,
    NotificationSettingTestResult,
    NotificationSettingUpdate,
)
from app.services.notification_setting_service import NotificationSettingService


class NotificationSettingController:
    def __init__(self, db: Session):
        self.service = NotificationSettingService(db)

    def get(self, user_id: int) -> NotificationSettingRead:
        return self.service.get(user_id)

    def update(self, user_id: int, payload: NotificationSettingUpdate) -> NotificationSettingRead:
        return self.service.update(user_id, payload)

    def send_test(self, user: User) -> NotificationSettingTestResult:
        return self.service.send_test_notification(user)
