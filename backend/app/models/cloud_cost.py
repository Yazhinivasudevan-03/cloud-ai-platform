"""CloudCost model: billing records used for cost dashboards and monthly cost prediction."""
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin


class CloudCost(TimestampMixin, Base):
    __tablename__ = "cloud_costs"
    __table_args__ = (
        Index("ix_cloud_costs_project_period", "project_id", "billing_period_start"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    service_name: Mapped[str] = mapped_column(String(100), nullable=False)
    cost_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    billing_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    billing_period_end: Mapped[date] = mapped_column(Date, nullable=False)

    project: Mapped["Project"] = relationship("Project", back_populates="cloud_costs")
