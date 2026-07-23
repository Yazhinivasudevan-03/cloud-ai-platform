"""CloudAccountAlertThreshold model: per-cloud-account overrides for the
CPU/memory alert engine's 3-tier thresholds (Phase 20). One row per
CloudProviderAccount (one-to-one) - any tier left null falls back to the
platform-wide Settings default for that tier, so an account only needs to
override the specific tiers it actually wants to change.

Scoped to CPU and memory only - the two metrics with real alert-evaluation
logic today (see AlertEvaluationService). Disk/network/cost/etc. threshold
fields are deliberately not modeled here: there is no real evaluator
reading those metrics into an Alert yet, and a threshold field with
nothing real behind it is exactly the kind of dead configuration surface
this project's own technical audit flagged as a problem elsewhere.
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

    cloud_provider_account: Mapped["CloudProviderAccount"] = relationship(
        "CloudProviderAccount", back_populates="alert_threshold"
    )
