"""Notification model: per-user delivery record for an alert across a channel."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin
from app.models.user import AUTH_SCHEMA


class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_read", "user_id", "is_read"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{AUTH_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # --- SMS delivery tracking (dynamic per-user phone numbers follow-up) ---
    # Populated only for channel="sms" rows - every other channel leaves
    # these honestly null rather than fabricating a value. Only a
    # deployment-scoped alert has a single associated cloud account
    # (see dispatcher.py's _recipients()); project/user/platform-wide
    # alerts leave cloud_provider_account_id null, never guessed.
    cloud_provider_account_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cloud_provider_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # A snapshot of the recipient's User.phone_number at send time, not a
    # live join - preserves what number an alert was actually sent to even
    # if the user later changes it.
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Twilio's real Message SID on a successful send.
    message_sid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # The real Twilio message status at send time ("queued", etc.) on
    # success, or the real failure reason/error detail on failure - never
    # a fabricated "delivered" (this platform has no delivery-status
    # webhook, so true delivery confirmation isn't tracked, only send-time
    # outcome).
    delivery_status: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="notifications")
    alert: Mapped["Alert"] = relationship("Alert", back_populates="notifications")
    cloud_provider_account: Mapped["CloudProviderAccount | None"] = relationship("CloudProviderAccount")

    # Phase 23: surfaces the same alert context the Notification Bell/history
    # need (severity, provider, region, resource, local+UTC alert time) by
    # reading straight through to the already-computed Alert properties
    # (Phase 22) - never re-derived, so there is exactly one source of truth.
    @property
    def severity(self) -> str | None:
        return self.alert.severity if self.alert else None

    @property
    def alert_type(self) -> str | None:
        return self.alert.alert_type if self.alert else None

    @property
    def provider(self) -> str | None:
        return self.alert.provider if self.alert else None

    @property
    def region(self) -> str | None:
        return self.alert.region if self.alert else None

    @property
    def resource(self) -> str | None:
        if self.alert is None:
            return None
        if self.alert.deployment is not None:
            return self.alert.deployment.name
        if self.alert.project is not None:
            return self.alert.project.name
        return None

    @property
    def alert_time_utc(self):
        return self.alert.alert_time_utc if self.alert else None

    @property
    def alert_time_local(self) -> str | None:
        return self.alert.alert_time_local if self.alert else None
