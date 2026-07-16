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
