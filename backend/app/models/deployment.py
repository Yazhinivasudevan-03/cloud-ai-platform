"""Deployment model: a running instance of a microservice in a Kubernetes namespace."""
from sqlalchemy import Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin


class Deployment(TimestampMixin, Base):
    __tablename__ = "deployments"
    __table_args__ = (
        UniqueConstraint(
            "microservice_id", "name", "namespace", name="uq_deployment_identity"
        ),
        Index("ix_deployments_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    microservice_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("microservices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    namespace: Mapped[str] = mapped_column(String(100), nullable=False, default="default")
    image: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    replicas: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="unknown")
    memory_limit_mb: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Configured memory limit per pod, in MB. Nullable - memory-based "
        "optimization recommendations (Phase 6) are skipped for deployments "
        "without one configured, since memory_usage_mb alone can't be turned "
        "into a utilization percentage without a limit to divide by.",
    )
    cloud_provider_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("cloud_provider_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="If set, this deployment's resource usage can be synced from "
        "real cloud provider telemetry using this account's credentials "
        "(Phase 12) - see app/services/cloud_sync_service.py.",
    )
    cloud_resource_identifier: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="The provider-specific resource this deployment maps to, e.g. "
        "an AWS EC2 instance ID - required alongside cloud_provider_account_id "
        "for cloud metric syncing to be possible.",
    )

    microservice: Mapped["Microservice"] = relationship(
        "Microservice", back_populates="deployments"
    )
    cloud_provider_account: Mapped["CloudProviderAccount | None"] = relationship(
        "CloudProviderAccount"
    )
    pods: Mapped[list["Pod"]] = relationship(
        "Pod", back_populates="deployment", cascade="all, delete-orphan"
    )
    metrics: Mapped[list["Metric"]] = relationship(
        "Metric", back_populates="deployment", cascade="all, delete-orphan"
    )
    resource_usages: Mapped[list["ResourceUsage"]] = relationship(
        "ResourceUsage", back_populates="deployment", cascade="all, delete-orphan"
    )
    predictions: Mapped[list["Prediction"]] = relationship(
        "Prediction", back_populates="deployment", cascade="all, delete-orphan"
    )
    anomaly_detections: Mapped[list["AnomalyDetection"]] = relationship(
        "AnomalyDetection", back_populates="deployment", cascade="all, delete-orphan"
    )
    failure_predictions: Mapped[list["FailurePrediction"]] = relationship(
        "FailurePrediction", back_populates="deployment", cascade="all, delete-orphan"
    )
    optimization_recommendations: Mapped[list["OptimizationRecommendation"]] = relationship(
        "OptimizationRecommendation", back_populates="deployment", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["Alert"]] = relationship(
        "Alert", back_populates="deployment", cascade="all, delete-orphan"
    )
