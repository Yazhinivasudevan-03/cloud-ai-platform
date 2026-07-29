"""Business logic for dynamic multi-cloud region discovery (Phase 25) -
discovers a CloudProviderAccount's available regions via the provider's own
API (see app/integrations/provider_factory.py), never a hardcoded list,
and keeps the result fresh both via a scheduled background job (see
register_cloud_region_sync_job in app/integrations/scheduler.py) and an
on-demand "Refresh Regions" call. Mirrors app/services/cloud_sync_service.py's
shape closely: per-account try/except tolerance in the "sync everything"
path, a real provider call in the single-account path that raises on
failure so the caller can surface the actual error.
"""
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.integrations.cloud_provider_client import CloudRegionInfo
from app.integrations.provider_factory import get_cloud_provider_client
from app.models.alert import Alert
from app.models.cloud_provider_account import CloudProviderAccount
from app.notifications.dispatcher import dispatch
from app.repositories.cloud_provider_account_repository import CloudProviderAccountRepository
from app.schemas.cloud_region import RegionSyncSummary
from app.utils.crypto import decrypt_credentials
from app.utils.exceptions import ForbiddenError, NotFoundError, ValidationAppError
from app.utils.logger import get_logger

logger = get_logger("cloud_region_sync")


@dataclass
class RegionSyncResult:
    account: CloudProviderAccount
    new_region_ids: list[str]


def load_available_regions(account: CloudProviderAccount) -> list[CloudRegionInfo]:
    """The full {id, display_name} pair for each region as of the last real
    sync (see sync_account) - stored in full, not just the id list, so a
    cached read (GET .../regions between syncs) can still show the real
    provider-returned label instead of falling back to the raw id."""
    try:
        stored = json.loads(account.available_regions)
    except (TypeError, ValueError):
        return []
    if not isinstance(stored, list):
        return []
    return [entry for entry in stored if isinstance(entry, dict) and "id" in entry]


class CloudRegionSyncService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = CloudProviderAccountRepository(db)

    def sync_account(self, account_id: int, current_user_id: int | None = None) -> RegionSyncResult:
        """Real, live region-discovery call for one account. Raises
        ValidationAppError/NotFoundError on failure (credentials_expired,
        unreachable provider, etc.) rather than silently leaving the stored
        region list untouched - the caller decides whether that's fatal
        (an on-demand refresh) or tolerable (the scheduled sweep, see
        sync_all_regions below). `current_user_id`, when given, is checked
        against the account's owner (self-service only, same as every other
        CloudProviderAccount operation)."""
        account = self.repository.get_by_id(account_id)
        if account is None:
            raise NotFoundError(f"Cloud provider account {account_id} not found", code="CLOUD_ACCOUNT_NOT_FOUND")
        if current_user_id is not None and account.user_id != current_user_id:
            raise ForbiddenError(
                "Cannot access another user's cloud provider account", code="NOT_YOUR_CLOUD_ACCOUNT"
            )

        try:
            credentials = decrypt_credentials(account.credentials_encrypted)
            client = get_cloud_provider_client(account.provider, credentials, account.region)
            discovered = client.list_regions()
        except ValidationAppError:
            account.connection_status = "ERROR"
            self.db.commit()
            raise

        previous_region_ids = {entry["id"] for entry in load_available_regions(account)}
        discovered_ids = [region["id"] for region in discovered]
        new_region_ids = [region_id for region_id in discovered_ids if region_id not in previous_region_ids]

        account.available_regions = json.dumps(discovered)
        account.last_region_sync = datetime.now(timezone.utc).replace(tzinfo=None)
        account.connection_status = "CONNECTED"
        self.db.commit()
        self.db.refresh(account)

        # Only notify once there was a real prior baseline - the very first
        # sync of a brand-new account populates available_regions for the
        # first time, which is expected setup, not a "new region appeared"
        # event worth alerting on.
        if new_region_ids and previous_region_ids:
            self._notify_new_regions(account, new_region_ids)

        return RegionSyncResult(account=account, new_region_ids=new_region_ids)

    def sync_all_regions(self) -> RegionSyncSummary:
        """Called by the scheduled job - syncs every connected account,
        tolerating individual failures (e.g. one account's credentials
        expired) without aborting the rest, matching
        CloudSyncService.sync_all()'s own tolerance."""
        accounts: list[CloudProviderAccount] = list(
            self.db.query(CloudProviderAccount)
            .filter(
                CloudProviderAccount.is_active.is_(True),
                CloudProviderAccount.credentials_validated.is_(True),
            )
            .all()
        )
        synced = 0
        failed = 0
        for account in accounts:
            try:
                self.sync_account(account.id)
                synced += 1
            except Exception:
                failed += 1
                logger.exception("Scheduled region sync failed for cloud account %s", account.id)
        return RegionSyncSummary(accounts_attempted=len(accounts), accounts_synced=synced, accounts_failed=failed)

    def _notify_new_regions(self, account: CloudProviderAccount, new_region_ids: list[str]) -> None:
        count = len(new_region_ids)
        region_word = "region" if count == 1 else "regions"
        message = (
            f"{count} new {account.provider} {region_word} now available for '{account.account_name}': "
            f"{', '.join(new_region_ids)}"
        )
        alert = Alert(
            user_id=account.user_id,
            alert_type="new_cloud_regions_available",
            severity="info",
            message=message,
            status="active",
            triggered_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        self.db.add(alert)
        self.db.flush()
        dispatch(self.db, alert)
        self.db.commit()
