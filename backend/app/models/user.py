"""User and Role models with a many-to-many association for RBAC.

Login credentials live in their own database (AUTH_SCHEMA, same MySQL
server as the rest of the application - see docs/PHASE_13.md), isolated
from all other application data. Every other model that references a user
(ApiKey, CloudProviderAccount, AuditLog, Notification, Setting, Project)
imports AUTH_SCHEMA from here to fully-qualify its ForeignKey target,
since MySQL requires cross-database foreign keys to name the schema
explicitly.
"""
from sqlalchemy import Boolean, Column, ForeignKey, Index, Integer, String, Table, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config.settings import get_settings
from app.database.base import Base
from app.models.mixins import TimestampMixin

AUTH_SCHEMA = get_settings().AUTH_MYSQL_DATABASE

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey(f"{AUTH_SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey(f"{AUTH_SCHEMA}.roles.id", ondelete="CASCADE"), primary_key=True),
    schema=AUTH_SCHEMA,
)


class Role(TimestampMixin, Base):
    """A named permission group (e.g. admin, operator, viewer)."""

    __tablename__ = "roles"
    __table_args__ = {"schema": AUTH_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    users: Mapped[list["User"]] = relationship(
        "User", secondary=user_roles, back_populates="roles"
    )


class User(TimestampMixin, Base):
    """A platform account. Passwords are stored as bcrypt hashes, never in plaintext."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_email_active", "email", "is_active"),
        {"schema": AUTH_SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str] = mapped_column(String(120), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        doc="E.164 format (e.g. +14155552671) - required for the sms notification channel (Phase 19).",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    roles: Mapped[list["Role"]] = relationship(
        "Role", secondary=user_roles, back_populates="users", lazy="selectin"
    )
    projects: Mapped[list["Project"]] = relationship("Project", back_populates="owner")
    api_keys: Mapped[list["ApiKey"]] = relationship(
        "ApiKey", back_populates="user", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan"
    )
    cloud_provider_accounts: Mapped[list["CloudProviderAccount"]] = relationship(
        "CloudProviderAccount", back_populates="user", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="user")
    settings: Mapped[list["Setting"]] = relationship(
        "Setting", back_populates="user", cascade="all, delete-orphan"
    )
    notification_setting: Mapped["NotificationSetting | None"] = relationship(
        "NotificationSetting", back_populates="user", cascade="all, delete-orphan", uselist=False
    )
