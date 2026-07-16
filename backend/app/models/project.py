"""Project model: the top-level container that groups microservices and cloud costs."""
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    owner: Mapped["User"] = relationship("User", back_populates="projects")
    microservices: Mapped[list["Microservice"]] = relationship(
        "Microservice", back_populates="project", cascade="all, delete-orphan"
    )
    cloud_costs: Mapped[list["CloudCost"]] = relationship(
        "CloudCost", back_populates="project", cascade="all, delete-orphan"
    )
