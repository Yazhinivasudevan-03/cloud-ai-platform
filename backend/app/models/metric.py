"""Metric model: raw time-series measurements collected from Prometheus exporters."""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin


class Metric(TimestampMixin, Base):
    __tablename__ = "metrics"
    __table_args__ = (
        Index("ix_metrics_lookup", "deployment_id", "metric_type", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deployment_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("deployments.id", ondelete="CASCADE"), nullable=True, index=True
    )
    pod_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("pods.id", ondelete="CASCADE"), nullable=True, index=True
    )
    metric_type: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    deployment: Mapped["Deployment"] = relationship("Deployment", back_populates="metrics")
    pod: Mapped["Pod"] = relationship("Pod", back_populates="metrics")
