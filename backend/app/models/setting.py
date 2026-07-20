"""Setting model: per-user or global key/value configuration entries."""
from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin
from app.models.user import AUTH_SCHEMA


class Setting(TimestampMixin, Base):
    __tablename__ = "settings"
    __table_args__ = (
        UniqueConstraint("user_id", "key", "scope", name="uq_setting_user_key_scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey(f"{AUTH_SCHEMA}.users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="user")

    user: Mapped["User"] = relationship("User", back_populates="settings")
