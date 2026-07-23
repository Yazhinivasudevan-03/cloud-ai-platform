"""CloudAccountAlertThreshold model: per-cloud-account overrides for the
CPU/memory/disk/network alert engine's 3-tier thresholds (Phase 20-21).
One row per CloudProviderAccount (one-to-one) - any tier left null falls
back to the platform-wide Settings default for that tier, so an account
only needs to override the specific tiers it actually wants to change.

Scoped to CPU/memory/disk/network only - the deployment-level metrics
with real alert-evaluation logic (see AlertEvaluationService). Cost is
deliberately NOT modeled here despite also being real now (Phase 21): it
is tracked per-project via CloudCost, not per-deployment/per-cloud-
account, so its own threshold overrides live on Project instead (see
Project.monthly_budget/cost_*_threshold) - a cloud account has no
consistent relationship to a project's total spend.
"""
from sqlalchemy import Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin


class CloudAccountAlertThreshold(TimestampMixin, Base):
    __tablename__ = "cloud_account_alert_thresholds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cloud_provider_account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("cloud_provider_accounts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    cpu_warning_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpu_critical_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpu_saturated_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_warning_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_critical_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_saturated_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_warning_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_critical_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_saturated_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    network_warning_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    network_critical_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    network_saturated_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)

    cloud_provider_account: Mapped["CloudProviderAccount"] = relationship(
        "CloudProviderAccount", back_populates="alert_threshold"
    )
