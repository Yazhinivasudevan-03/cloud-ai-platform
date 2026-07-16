"""AnomalyDetection model: Isolation-Forest output flagging abnormal metric behaviour."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin


class AnomalyDetection(TimestampMixin, Base):
    __tablename__ = "anomaly_detections"
    __table_args__ = (
        Index("ix_anomaly_deployment_time", "deployment_id", "detected_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deployment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_type: Mapped[str] = mapped_column(String(50), nullable=False)
    anomaly_score: Mapped[float] = mapped_column(Float, nullable=False)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)

    deployment: Mapped["Deployment"] = relationship(
        "Deployment", back_populates="anomaly_detections"
    )
