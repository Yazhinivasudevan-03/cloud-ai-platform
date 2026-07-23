"""Business logic for per-user notification preferences (Phase 20)."""
from sqlalchemy.orm import Session

from app.models.notification_setting import NotificationSetting
from app.models.user import User
from app.notifications.email_notifier import send_email
from app.notifications.slack_notifier import send_slack_message
from app.notifications.sms_notifier import send_sms
from app.notifications.telegram_notifier import send_telegram_message
from app.repositories.notification_setting_repository import NotificationSettingRepository
from app.schemas.notification_setting import (
    NotificationSettingRead,
    NotificationSettingTestResult,
    NotificationSettingUpdate,
)
from app.utils.crypto import decrypt_credentials, encrypt_credentials

_CREDENTIAL_KEYS = ("telegram_bot_token", "telegram_chat_id", "slack_webhook_url", "teams_webhook_url")
_SIMPLE_FIELDS = (
    "email_enabled",
    "sms_enabled",
    "telegram_enabled",
    "slack_enabled",
    "teams_enabled",
    "instant_alerts_enabled",
    "daily_summary_enabled",
    "alert_sound_enabled",
    "dnd_start_time",
    "dnd_end_time",
    "timezone",
)


class NotificationSettingService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = NotificationSettingRepository(db)

    def decrypt(self, setting: NotificationSetting) -> dict[str, str]:
        if not setting.credentials_encrypted:
            return {}
        return decrypt_credentials(setting.credentials_encrypted)

    def get(self, user_id: int) -> NotificationSettingRead:
        return self._to_read(self.repository.get_or_create(user_id))

    def _to_read(self, setting: NotificationSetting) -> NotificationSettingRead:
        creds = self.decrypt(setting)
        return NotificationSettingRead(
            email_enabled=setting.email_enabled,
            sms_enabled=setting.sms_enabled,
            telegram_enabled=setting.telegram_enabled,
            slack_enabled=setting.slack_enabled,
            teams_enabled=setting.teams_enabled,
            instant_alerts_enabled=setting.instant_alerts_enabled,
            daily_summary_enabled=setting.daily_summary_enabled,
            alert_sound_enabled=setting.alert_sound_enabled,
            dnd_start_time=setting.dnd_start_time,
            dnd_end_time=setting.dnd_end_time,
            timezone=setting.timezone,
            telegram_bot_token_configured=bool(creds.get("telegram_bot_token")),
            telegram_chat_id_configured=bool(creds.get("telegram_chat_id")),
            slack_webhook_configured=bool(creds.get("slack_webhook_url")),
            teams_webhook_configured=bool(creds.get("teams_webhook_url")),
        )

    def update(self, user_id: int, payload: NotificationSettingUpdate) -> NotificationSettingRead:
        setting = self.repository.get_or_create(user_id)
        data = payload.model_dump(exclude_unset=True)

        for field in _SIMPLE_FIELDS:
            if field in data:
                setattr(setting, field, data[field])

        if any(key in data for key in _CREDENTIAL_KEYS):
            creds = self.decrypt(setting)
            for key in _CREDENTIAL_KEYS:
                if key not in data:
                    continue
                value = data[key]
                if value:
                    creds[key] = value
                else:
                    creds.pop(key, None)  # explicit empty string clears that credential
            setting.credentials_encrypted = encrypt_credentials(creds) if creds else None

        self.db.commit()
        self.db.refresh(setting)
        return self._to_read(setting)

    def send_test_notification(self, user: User) -> NotificationSettingTestResult:
        """Sends a real notification through every channel the user has
        enabled right now, regardless of do-not-disturb - a test the user
        explicitly asked for should never be silently swallowed."""
        setting = self.repository.get_or_create(user.id)
        creds = self.decrypt(setting)
        text = (
            "This is a test notification from Cloud AI Platform - your alert "
            "delivery is configured correctly."
        )

        result = NotificationSettingTestResult()
        if setting.email_enabled:
            result.email_sent = send_email(user.email, "Test Notification", text)
        if setting.sms_enabled:
            result.sms_sent = send_sms(user.phone_number, text)
        if setting.telegram_enabled:
            result.telegram_sent = send_telegram_message(
                text,
                bot_token=creds.get("telegram_bot_token"),
                chat_id=creds.get("telegram_chat_id"),
            )
        if setting.slack_enabled:
            result.slack_sent = send_slack_message(text, webhook_url=creds.get("slack_webhook_url"))
        return result
