"""Declarative base class shared by every SQLAlchemy ORM model in the platform."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """All ORM models inherit from this class so they share one MetaData registry,
    which Alembic uses for autogeneration and the test suite uses for schema creation."""

    pass
