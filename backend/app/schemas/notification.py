"""Pydantic schemas for the Notification resource."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    alert_id: int | None
    channel: str
    message: str
    is_read: bool
    sent_at: datetime | None
    created_at: datetime
    # Phase 23 - the same alert context the Notification Bell/history show,
    # read through to the linked Alert; null for a notification with no
    # alert_id, or whose alert resolves no timezone/deployment/project.
    severity: str | None = None
    alert_type: str | None = None
    provider: str | None = None
    region: str | None = None
    resource: str | None = None
    alert_time_utc: datetime | None = None
    alert_time_local: str | None = None
    # SMS delivery tracking - populated only for channel="sms" rows, null
    # for every other channel (never fabricated).
    cloud_provider_account_id: int | None = None
    phone_number: str | None = None
    message_sid: str | None = None
    delivery_status: str | None = None


class NotificationSummary(BaseModel):
    """Powers the Notification Bell (Phase 23): unread counts by severity,
    plus the total unread count for the badge."""

    unread_total: int
    critical_count: int
    warning_count: int
    info_count: int
