"""Pod model: an individual Kubernetes pod belonging to a deployment."""
from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin


class Pod(TimestampMixin, Base):
    __tablename__ = "pods"
    __table_args__ = (
        UniqueConstraint("deployment_id", "pod_name", name="uq_pod_identity"),
        Index("ix_pods_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deployment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pod_name: Mapped[str] = mapped_column(String(150), nullable=False)
    node_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="unknown")
    restart_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    deployment: Mapped["Deployment"] = relationship("Deployment", back_populates="pods")
    metrics: Mapped[list["Metric"]] = relationship(
        "Metric", back_populates="pod", cascade="all, delete-orphan"
    )
    failure_predictions: Mapped[list["FailurePrediction"]] = relationship(
        "FailurePrediction", back_populates="pod", cascade="all, delete-orphan"
    )
