"""Reusable mixins for SQLAlchemy ORM models."""
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """Adds `created_at` / `updated_at` columns, populated by the database server.

    Every table in the platform includes these two columns per the project's
    data-modelling standard, so every model composes this mixin instead of
    redeclaring the columns.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
