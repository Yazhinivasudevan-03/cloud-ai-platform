"""CloudResourceMetric model: a real CloudWatch datapoint for one discovered
EC2 instance (Phase 29) - collected automatically by
app/services/cloud_resource_discovery_service.py on every discovery cycle
for every active, running ec2_instance CloudResource. Scoped to EC2 only
in this phase, matching the exact metric set AWS/EC2's basic-monitoring
CloudWatch namespace (plus the best-effort CWAgent namespace for memory)
actually publishes - see app/integrations/aws_cloudwatch.py's
fetch_ec2_full_metrics.
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin


class CloudResourceMetric(TimestampMixin, Base):
    __tablename__ = "cloud_resource_metrics"
    __table_args__ = (
        Index("ix_cloud_resource_metrics_resource_time", "cloud_resource_id", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cloud_resource_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cloud_resources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cpu_usage_percent: Mapped[float] = mapped_column(Float, nullable=False)
    network_in_kbps: Mapped[float] = mapped_column(Float, nullable=False)
    network_out_kbps: Mapped[float] = mapped_column(Float, nullable=False)
    disk_read_bytes: Mapped[float] = mapped_column(Float, nullable=False)
    disk_write_bytes: Mapped[float] = mapped_column(Float, nullable=False)
    # 0 = passed, 1 = failed, NULL = CloudWatch reported no status-check
    # datapoint for the lookback window.
    status_check_failed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Best-effort via the CWAgent namespace - NULL (not 0.0) when the agent
    # isn't installed, honestly disclosing "unknown" rather than fabricating
    # "zero usage" (see fetch_ec2_full_metrics's own docstring).
    memory_usage_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    cloud_resource: Mapped["CloudResource"] = relationship("CloudResource", back_populates="metrics")
