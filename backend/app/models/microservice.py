"""Microservice model: a deployable service that belongs to a project."""
from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin


class Microservice(TimestampMixin, Base):
    __tablename__ = "microservices"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_microservice_project_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    repository_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="microservices")
    deployments: Mapped[list["Deployment"]] = relationship(
        "Deployment", back_populates="microservice", cascade="all, delete-orphan"
    )
