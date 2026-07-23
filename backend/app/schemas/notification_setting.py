"""Pydantic schemas for the NotificationSetting resource.

Channel credentials (Telegram bot token/chat ID, Slack/Teams webhook URLs)
are write-only, mirroring CloudProviderAccountRead: a client can set or
overwrite them but can never read a previously stored secret back out.
`NotificationSettingRead` instead reports a `*_configured` boolean per
credential so the UI can show "already set" without exposing the value.
"""
from datetime import time

from pydantic import BaseModel, Field


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


class NotificationSettingTestResult(BaseModel):
    email_sent: bool | None = None
    sms_sent: bool | None = None
    telegram_sent: bool | None = None
    slack_sent: bool | None = None
