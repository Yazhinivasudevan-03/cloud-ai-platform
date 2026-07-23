"""Self-service notification settings endpoints - every user reads/updates
only their own preferences and can send themselves a real test message."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.authentication.dependencies import get_current_active_user
from app.config.settings import get_settings
from app.controllers.notification_setting_controller import NotificationSettingController
from app.database.session import get_db
from app.middleware.rate_limiter import limiter
from app.models.user import User
from app.schemas.notification_setting import (
    NotificationSettingRead,
    NotificationSettingTestResult,
    NotificationSettingUpdate,
)

settings = get_settings()

router = APIRouter(prefix="/notification-settings", tags=["Notification Settings"])


@router.get(
    "",
    response_model=NotificationSettingRead,
    summary="Get the current user's own notification preferences",
)
def get_notification_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> NotificationSettingRead:
    return NotificationSettingController(db).get(current_user.id)


@router.put(
    "",
    response_model=NotificationSettingRead,
    summary="Update the current user's own notification preferences",
)
def update_notification_settings(
    payload: NotificationSettingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> NotificationSettingRead:
    return NotificationSettingController(db).update(current_user.id, payload)


@router.post(
    "/test",
    response_model=NotificationSettingTestResult,
    summary="Send a real test notification through every channel the current user has enabled",
)
@limiter.limit(settings.RATE_LIMIT_NOTIFICATION_TEST)
def test_notification_settings(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> NotificationSettingTestResult:
    return NotificationSettingController(db).send_test(current_user)
