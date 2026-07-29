"""Business logic for the read-only cloud resource inventory (Phase 25C) -
lists a connected cloud account's real compute/cluster/database/storage/
networking resources via the same CloudProviderClient interface region
discovery and monitoring already use (app/integrations/provider_factory.py).

The "all regions" aggregation loop lives here, once, rather than being
duplicated inside every provider adapter - each adapter's list_* methods
only ever need to handle a single, already-resolved region.
"""
from sqlalchemy.orm import Session

from app.integrations.cloud_provider_client import CloudProviderClient, CloudResourceSummary
from app.integrations.provider_factory import get_cloud_provider_client
from app.repositories.cloud_provider_account_repository import CloudProviderAccountRepository
from app.schemas.cloud_resource import RESOURCE_CATEGORIES
from app.services.cloud_region_sync_service import load_available_regions
from app.utils.crypto import decrypt_credentials
from app.utils.exceptions import ForbiddenError, NotFoundError, ValidationAppError

ALL_REGIONS_SENTINEL = "all"

_CATEGORY_METHODS: dict[str, str] = {
    "compute": "list_resources",
    "clusters": "list_clusters",
    "databases": "list_databases",
    "storage": "list_storage",
    "networking": "list_networking",
}


class CloudResourceInventoryService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = CloudProviderAccountRepository(db)

    def list_resources(
        self, account_id: int, current_user_id: int, category: str, region: str
    ) -> list[CloudResourceSummary]:
        if category not in RESOURCE_CATEGORIES:
            raise ValidationAppError(
                f"'{category}' is not a valid resource category - use one of {', '.join(RESOURCE_CATEGORIES)}",
                code="INVALID_RESOURCE_CATEGORY",
            )

        account = self.repository.get_by_id(account_id)
        if account is None:
            raise NotFoundError(f"Cloud provider account {account_id} not found", code="CLOUD_ACCOUNT_NOT_FOUND")
        if account.user_id != current_user_id:
            raise ForbiddenError(
                "Cannot access another user's cloud provider account", code="NOT_YOUR_CLOUD_ACCOUNT"
            )

        credentials = decrypt_credentials(account.credentials_encrypted)
        client = get_cloud_provider_client(account.provider, credentials, account.region)
        method = getattr(client, _CATEGORY_METHODS[category])

        if region == ALL_REGIONS_SENTINEL:
            return self._list_across_all_regions(client, method, account)
        return method(region)

    def _list_across_all_regions(
        self, client: CloudProviderClient, method, account
    ) -> list[CloudResourceSummary]:
        available_regions = load_available_regions(account)
        if not available_regions:
            raise ValidationAppError(
                "This account has no discovered regions yet - refresh regions before requesting "
                "an 'all regions' resource listing",
                code="NO_REGIONS_DISCOVERED",
            )

        results: list[CloudResourceSummary] = []
        for region_entry in available_regions:
            # Tolerant per-region: one region rejecting the request (e.g. a
            # service not enabled there) must not blank out every other
            # region's real results - matches CloudSyncService.sync_all()'s
            # own per-item tolerance.
            try:
                results.extend(method(region_entry["id"]))
            except ValidationAppError:
                continue
        return results
