"""User and Role models with a many-to-many association for RBAC.

Login credentials live in their own database (AUTH_SCHEMA, same MySQL
server as the rest of the application - see docs/PHASE_13.md), isolated
from all other application data. Every other model that references a user
(ApiKey, CloudProviderAccount, AuditLog, Notification, Setting, Project)
imports AUTH_SCHEMA from here to fully-qualify its ForeignKey target,
since MySQL requires cross-database foreign keys to name the schema
explicitly.
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Table, UniqueConstraint
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
        doc="E.164 format (e.g. +14155552671) - required for the sms notification channel (Phase 19). "
        "Also doubles as the signup form's 'Mobile Number' field (Phase 24) - not duplicated.",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        doc="The actual platform operator flag (Phase 24) - distinct from the 'admin' role, which is "
        "now a tenant's own app-management capability, not a cross-tenant data-access bypass. Only "
        "is_superuser can see platform-wide, unowned alerts (API Latency/Error Rate/Node Failure/"
        "Container Failure).",
    )

    # Signup fields (Phase 24) - multi-tenant SaaS onboarding. Nullable so
    # existing pre-Phase-24 users are unaffected; new registrations require
    # them via UserCreate's own validation.
    first_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    country: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # Email verification (Phase 24). Existing pre-Phase-24 users are
    # backfilled to already-verified by the migration (server_default),
    # so nobody already using the platform gets locked out; new
    # registrations default to unverified at the Python/ORM level and
    # must verify before their first login. The token is stored as a
    # SHA-256 hash, never in plaintext - mirrors why passwords are hashed,
    # not reversible, even though this is a random opaque token rather
    # than a low-entropy secret a user chose themselves.
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verification_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email_verification_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Password reset (Phase 24) - same hashed-token convention.
    password_reset_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    password_reset_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

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
