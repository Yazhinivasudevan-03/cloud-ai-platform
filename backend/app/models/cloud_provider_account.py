"""CloudProviderAccount model: a user's own configured cloud provider
credentials (AWS/Azure/GCP/other), self-service and unrestricted in count -
any authenticated user may register any number of accounts, each scoped to
one cloud region. Credentials are stored encrypted (see app/utils/crypto.py)
and are never serialized back out through the API - see
CloudProviderAccountRead in app/schemas/cloud_provider_account.py."""
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin
from app.models.user import AUTH_SCHEMA


class CloudProviderAccount(TimestampMixin, Base):
    __tablename__ = "cloud_provider_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "account_name", name="uq_cloud_account_user_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{AUTH_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Free-text rather than a fixed enum, deliberately: the requirement is
    # "any cloud provider", not a hardcoded AWS/Azure/GCP list - a provider
    # value the frontend doesn't have a dedicated icon/label for still works,
    # it just renders under a generic "other" treatment client-side.
    provider: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    account_name: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    account_identifier: Mapped[str | None] = mapped_column(
        String(100), nullable=True, doc="e.g. AWS Account ID, Azure Subscription ID, GCP Project ID"
    )
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    user: Mapped["User"] = relationship("User", back_populates="cloud_provider_accounts")
