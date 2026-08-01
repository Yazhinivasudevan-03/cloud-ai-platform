"""CloudProviderAccount model: a user's own configured cloud provider
credentials (AWS/Azure/GCP/other), self-service and unrestricted in count -
any authenticated user may register any number of accounts, each scoped to
one cloud region. Credentials are stored encrypted (see app/utils/crypto.py)
and are never serialized back out through the API - see
CloudProviderAccountRead in app/schemas/cloud_provider_account.py."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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
    # The account's *currently selected* region (Phase 25 - previously this
    # was simply "the one region this account is scoped to", before region
    # discovery existed). Every existing caller that reads this column
    # (CloudSyncService, CloudCostService, etc.) is unaffected - it still
    # means "use this region for this account's requests". The literal
    # value "all" is a valid sentinel meaning "aggregate across every
    # region in available_regions" (see CloudResourceInventoryService).
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    account_identifier: Mapped[str | None] = mapped_column(
        String(100), nullable=True, doc="e.g. AWS Account ID, Azure Subscription ID, GCP Project ID"
    )
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # --- Phase 25: dynamic region discovery ---
    # JSON-encoded list[str] of region IDs discovered from the provider's
    # own API (see app/services/cloud_region_sync_service.py) - never
    # hardcoded. Empty ("[]") until the first successful sync. Stored as
    # Text/JSON-encoded rather than a native JSON column, matching this
    # project's existing convention (see NotificationSetting.alert_preferences).
    available_regions: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    last_region_sync: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # CONNECTED / ERROR / CREDENTIALS_EXPIRED - reflects the outcome of the
    # most recent region sync attempt (or "CONNECTED" for an account that
    # has never been synced yet, matching today's implicit assumption that
    # a newly-created account's credentials are valid until proven otherwise).
    connection_status: Mapped[str] = mapped_column(String(30), nullable=False, default="CONNECTED")

    # --- Credential configuration workflow ---
    # Whether the currently-stored credentials have actually been proven to
    # work via a real test_connection() call (STS GetCallerIdentity for AWS,
    # the provider's own equivalent elsewhere) - distinct from
    # connection_status, which only reflects the *region sync's* outcome.
    # False for a newly-created/edited account until POST
    # /{id}/validate-credentials succeeds; pre-existing accounts are
    # backfilled True by the migration (preserving today's implicit
    # "already connected = already trusted" behavior). Scheduled sync sweeps
    # (CloudSyncService.sync_all, CloudRegionSyncService.sync_all_regions)
    # skip any account where this is False, so monitoring never runs against
    # known-unconfigured credentials.
    credentials_validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    credentials_validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # --- Phase 29: automatic resource discovery ---
    # Reflects the outcome of the most recent CloudResourceDiscoveryService
    # run for this account (on-connect best-effort call, the scheduled
    # sweep, or a manual "Discover Now"). last_discovery_error is the
    # provider's own real error message, verbatim - never a generic "0
    # resources found" when discovery actually failed (see
    # CloudResourceDiscoveryService.discover_account).
    last_discovery_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_discovery_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="cloud_provider_accounts")
    alert_threshold: Mapped["CloudAccountAlertThreshold | None"] = relationship(
        "CloudAccountAlertThreshold",
        back_populates="cloud_provider_account",
        cascade="all, delete-orphan",
        uselist=False,
    )
    timezones: Mapped[list["CloudAccountTimezone"]] = relationship(
        "CloudAccountTimezone",
        back_populates="cloud_provider_account",
        cascade="all, delete-orphan",
    )
