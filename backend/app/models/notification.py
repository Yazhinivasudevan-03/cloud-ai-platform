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

    user: Mapped["User"] = relationship("User", back_populates="notifications")
    alert: Mapped["Alert"] = relationship("Alert", back_populates="notifications")

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
