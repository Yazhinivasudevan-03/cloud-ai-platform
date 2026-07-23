"""NotificationSetting model: per-user alert delivery preferences (Phase 20).

One row per user (one-to-one). Channel credentials that need to be kept
secret (Telegram bot token/chat ID, Slack/Teams webhook URLs) are stored
as a single encrypted JSON blob via app/utils/crypto.py - the same
Fernet-based encrypt_credentials/decrypt_credentials already used for
CloudProviderAccount, rather than inventing a second encryption scheme.
Any key left out of that blob (or blank) means "fall back to the
platform-wide setting" (see app/notifications/dispatcher.py), so a user
isn't forced to run their own Telegram bot just to receive alerts through
a shared one - they only need to supply their own chat ID.

Email and SMS have no separate address field here - they reuse
User.email/User.phone_number directly rather than duplicating an address
this platform already has.
"""
from datetime import time

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin
from app.models.user import AUTH_SCHEMA


class NotificationSetting(TimestampMixin, Base):
    __tablename__ = "notification_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{AUTH_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sms_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    telegram_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    slack_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    teams_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Encrypted JSON blob: {"telegram_bot_token": ..., "telegram_chat_id": ...,
    # "slack_webhook_url": ..., "teams_webhook_url": ...}. Write-only from the
    # API's perspective, mirroring CloudProviderAccountRead - see
    # NotificationSettingRead.
    credentials_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    instant_alerts_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    daily_summary_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    alert_sound_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Do-not-disturb window in the timezone below - both null means DND is
    # off. A window that wraps midnight (e.g. 22:00-07:00) is valid and
    # handled explicitly by the dispatcher, not assumed away.
    dnd_start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    dnd_end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="UTC")

    user: Mapped["User"] = relationship("User", back_populates="notification_setting")
