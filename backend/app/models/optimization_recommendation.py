"""OptimizationRecommendation model: actionable suggestions produced by the optimization engine."""
from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin


class OptimizationRecommendation(TimestampMixin, Base):
    __tablename__ = "optimization_recommendations"
    __table_args__ = (
        Index("ix_optimization_deployment_status", "deployment_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deployment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recommendation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_savings: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    deployment: Mapped["Deployment"] = relationship(
        "Deployment", back_populates="optimization_recommendations"
    )
