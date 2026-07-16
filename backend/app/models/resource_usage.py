"""ResourceUsage model: periodic aggregated CPU/memory/disk/network snapshots per deployment."""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin


class ResourceUsage(TimestampMixin, Base):
    __tablename__ = "resource_usage"
    __table_args__ = (
        Index("ix_resource_usage_deployment_time", "deployment_id", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deployment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cpu_usage_percent: Mapped[float] = mapped_column(Float, nullable=False)
    memory_usage_mb: Mapped[float] = mapped_column(Float, nullable=False)
    disk_usage_mb: Mapped[float] = mapped_column(Float, nullable=False)
    network_in_kbps: Mapped[float] = mapped_column(Float, nullable=False)
    network_out_kbps: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    deployment: Mapped["Deployment"] = relationship(
        "Deployment", back_populates="resource_usages"
    )
