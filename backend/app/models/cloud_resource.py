"""CloudResource model: a real, discovered resource in a connected cloud
provider account (Phase 29) - the persisted counterpart to the live-only
inventory Phase 25C already exposes via GET .../resources. Populated and
kept fresh by app/services/cloud_resource_discovery_service.py, never
hand-entered by a user (contrast with Deployment.cloud_resource_identifier,
which is manually typed in).

`is_active` is the mechanism behind automatic appear/disappear: a
discovery pass flips it to False for any previously-seen resource it no
longer observes (terminated/deleted in the real provider), rather than
deleting the row outright, so resource history isn't destroyed by a
disappearance.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin
from app.models.user import AUTH_SCHEMA


class CloudResource(TimestampMixin, Base):
    __tablename__ = "cloud_resources"
    __table_args__ = (
        UniqueConstraint(
            "cloud_provider_account_id",
            "resource_type",
            "region",
            "external_id",
            name="uq_cloud_resource_identity",
        ),
        Index("ix_cloud_resources_account_type", "cloud_provider_account_id", "resource_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{AUTH_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cloud_provider_account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cloud_provider_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    # Free-text, not an enum - deliberately matches this project's existing
    # convention (see CloudProviderAccount.provider) so a resource type a
    # future provider adapter introduces needs no schema change here.
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(
        String(255), nullable=False, doc="The provider's own real resource ID/ARN, e.g. an EC2 instance ID"
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    availability_zone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    instance_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    public_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    private_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    # JSON-encoded, matching this project's existing convention for
    # semi-structured columns (see NotificationSetting.alert_preferences,
    # CloudProviderAccount.available_regions) rather than a native JSON
    # column type.
    tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_json: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="Resource-type-specific extras that don't fit the common columns above"
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    user: Mapped["User"] = relationship("User")
    cloud_provider_account: Mapped["CloudProviderAccount"] = relationship("CloudProviderAccount")
    metrics: Mapped[list["CloudResourceMetric"]] = relationship(
        "CloudResourceMetric", back_populates="cloud_resource", cascade="all, delete-orphan"
    )
