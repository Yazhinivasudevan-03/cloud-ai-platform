"""Project model: the top-level container that groups microservices and cloud costs."""
from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin
from app.models.user import AUTH_SCHEMA


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{AUTH_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Cost alerting (Phase 21) - nullable; skipped entirely for a project
    # with no configured budget, the same guard every other threshold-based
    # alert type uses for its own limit field. Cost is tracked per-project
    # (via CloudCost), not per-cloud-account, so its threshold overrides
    # live here rather than on CloudAccountAlertThreshold.
    monthly_budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_warning_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_critical_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_saturated_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)

    owner: Mapped["User"] = relationship("User", back_populates="projects")
    microservices: Mapped[list["Microservice"]] = relationship(
        "Microservice", back_populates="project", cascade="all, delete-orphan"
    )
    cloud_costs: Mapped[list["CloudCost"]] = relationship(
        "CloudCost", back_populates="project", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["Alert"]] = relationship(
        "Alert", back_populates="project", cascade="all, delete-orphan"
    )
