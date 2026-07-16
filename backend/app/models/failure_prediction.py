"""FailurePrediction model: Random-Forest output estimating probability of failure."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin


class FailurePrediction(TimestampMixin, Base):
    __tablename__ = "failure_predictions"
    __table_args__ = (
        Index("ix_failure_pred_deployment_time", "deployment_id", "predicted_at"),
        CheckConstraint(
            "probability >= 0 AND probability <= 1", name="ck_failure_prediction_probability_range"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deployment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pod_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("pods.id", ondelete="CASCADE"), nullable=True, index=True
    )
    failure_type: Mapped[str] = mapped_column(String(50), nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    deployment: Mapped["Deployment"] = relationship(
        "Deployment", back_populates="failure_predictions"
    )
    pod: Mapped["Pod"] = relationship("Pod", back_populates="failure_predictions")
