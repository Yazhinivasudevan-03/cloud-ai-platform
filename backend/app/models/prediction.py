"""Prediction model: LSTM-generated workload forecasts with a confidence score."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin


class Prediction(TimestampMixin, Base):
    __tablename__ = "predictions"
    __table_args__ = (
        Index("ix_predictions_deployment_target", "deployment_id", "target_timestamp"),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1", name="ck_prediction_confidence_range"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deployment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_type: Mapped[str] = mapped_column(String(30), nullable=False, default="lstm")
    metric_type: Mapped[str] = mapped_column(String(50), nullable=False)
    predicted_value: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    target_timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    deployment: Mapped["Deployment"] = relationship("Deployment", back_populates="predictions")
