"""Pydantic schemas for the NotificationSetting resource.

Channel credentials (Telegram bot token/chat ID, Slack/Teams webhook URLs)
are write-only, mirroring CloudProviderAccountRead: a client can set or
overwrite them but can never read a previously stored secret back out.
`NotificationSettingRead` instead reports a `*_configured` boolean per
credential so the UI can show "already set" without exposing the value.
"""
import re
from datetime import time

from pydantic import BaseModel, Field, field_validator

from app.notifications.alert_preferences import ALL_CATEGORIES, default_preferences

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AlertCategoryPreference(BaseModel):
    enabled: bool = True
    # Ignored for the 4 simple (non-tiered) categories - see
    # app/notifications/alert_preferences.py's SIMPLE_CATEGORIES.
    warning: bool = True
    critical: bool = True
    saturated: bool = True


class NotificationSettingUpdate(BaseModel):
    email_enabled: bool | None = None
    sms_enabled: bool | None = None
    telegram_enabled: bool | None = None
    slack_enabled: bool | None = None
    teams_enabled: bool | None = None
    instant_alerts_enabled: bool | None = None
    daily_summary_enabled: bool | None = None
    alert_sound_enabled: bool | None = None
    dnd_start_time: time | None = None
    dnd_end_time: time | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=50)

    # Write-only credential overrides - any left unset here keep whatever
    # was previously stored; sending an explicit empty string clears that
    # one credential (falls back to the platform-wide setting again).
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    slack_webhook_url: str | None = None
    teams_webhook_url: str | None = None

    # Personal contact info (Phase 23). Primary email/phone stay on User
    # (see PATCH /auth/me) - these are the fields with no existing home.
    secondary_email: str | None = Field(default=None, max_length=120)
    country_code: str | None = Field(default=None, max_length=6)
    telegram_username: str | None = Field(default=None, max_length=100)
    notification_language: str | None = Field(default=None, min_length=2, max_length=10)
    alert_preferences: dict[str, AlertCategoryPreference] | None = None

    @field_validator("secondary_email")
    @classmethod
    def validate_secondary_email(cls, value: str | None) -> str | None:
        # An explicit empty string clears the field (matches the
        # credential-clearing convention above) - only a non-empty value
        # is validated as looking like an email address.
        if value and not _EMAIL_PATTERN.match(value):
            raise ValueError("secondary_email must be a valid email address")
        return value


class NotificationSettingRead(BaseModel):
    email_enabled: bool
    sms_enabled: bool
    telegram_enabled: bool
    slack_enabled: bool
    teams_enabled: bool
    instant_alerts_enabled: bool
    daily_summary_enabled: bool
    alert_sound_enabled: bool
    dnd_start_time: time | None
    dnd_end_time: time | None
    timezone: str
    telegram_bot_token_configured: bool
    telegram_chat_id_configured: bool
    slack_webhook_configured: bool
    teams_webhook_configured: bool
    secondary_email: str | None
    country_code: str | None
    telegram_username: str | None
    notification_language: str
    alert_preferences: dict[str, AlertCategoryPreference] = Field(default_factory=default_preferences)


class NotificationSettingTestResult(BaseModel):
    email_sent: bool | None = None
    secondary_email_sent: bool | None = None
    sms_sent: bool | None = None
    telegram_sent: bool | None = None
    slack_sent: bool | None = None
