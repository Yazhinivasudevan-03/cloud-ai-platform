"""Alert model: threshold-triggered warnings (60% / 80% / 100%) surfaced to operators."""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin


class Alert(TimestampMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_status_severity", "status", "severity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deployment_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("deployments.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Cost alerts (Phase 21) are project-scoped, not deployment-scoped -
    # spend is tracked per-project via CloudCost, so there is no single
    # deployment a cost alert could sensibly attach to. Exactly one of
    # deployment_id/project_id is set per alert in practice (enforced by
    # AlertEvaluationService, not a DB constraint).
    project_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    threshold_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    triggered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    deployment: Mapped["Deployment"] = relationship("Deployment", back_populates="alerts")
    project: Mapped["Project | None"] = relationship("Project", back_populates="alerts")
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="alert", cascade="all, delete-orphan"
    )
