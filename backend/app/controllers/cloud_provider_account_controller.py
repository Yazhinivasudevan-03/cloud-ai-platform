"""Controller layer for a user's own CloudProviderAccount endpoints."""
import math
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models.cloud_provider_account import CloudProviderAccount
from app.schemas.alert import AlertRead
from app.schemas.cloud_provider_account import (
    CloudAccountDeploymentSummary,
    ConnectionTestResultRead,
    CloudProviderAccountCreate,
    CloudProviderAccountRead,
    CloudProviderAccountUpdate,
    TestConnectionRequest,
)
from app.schemas.cloud_region import CloudAccountRegionsRead
from app.schemas.cloud_resource import CloudResourceListRead, CloudResourceRead
from app.schemas.cloud_resource_discovery import (
    CloudAccountDiscoverySummary,
    DiscoveredResourceListRead,
    DiscoveredResourceRead,
    Ec2MetricRead,
)
from app.schemas.common import PaginatedResponse, PaginationMeta
from app.schemas.resource_usage import ResourceUsageRead
from app.services.cloud_provider_account_service import CloudProviderAccountService
from app.services.cloud_provisioning_service import CloudProvisioningService
from app.services.cloud_region_sync_service import CloudRegionSyncService, load_available_regions
from app.services.cloud_resource_discovery_service import CloudResourceDiscoveryService
from app.services.cloud_resource_inventory_service import CloudResourceInventoryService


def _regions_read(account: CloudProviderAccount) -> CloudAccountRegionsRead:
    return CloudAccountRegionsRead(
        selected_region=account.region,
        regions=load_available_regions(account),
        last_region_sync=account.last_region_sync,
        connection_status=account.connection_status,
    )


class CloudProviderAccountController:
    def __init__(self, db: Session):
        self.db = db
        self.service = CloudProviderAccountService(db)
        self.region_sync_service = CloudRegionSyncService(db)
        self.resource_inventory_service = CloudResourceInventoryService(db)
        self.provisioning_service = CloudProvisioningService(db)
        self.discovery_service = CloudResourceDiscoveryService(db)

    def create(self, user_id: int, payload: CloudProviderAccountCreate) -> CloudProviderAccountRead:
        return CloudProviderAccountRead.model_validate(self.service.create(user_id, payload))

    def test_connection(self, payload: TestConnectionRequest) -> ConnectionTestResultRead:
        result = self.service.test_connection(payload.provider, payload.region, payload.credentials)
        return ConnectionTestResultRead(**result)

    def validate_credentials(self, account_id: int, current_user_id: int) -> ConnectionTestResultRead:
        result = self.service.validate_credentials(account_id, current_user_id)
        # Kicks off real monitoring immediately rather than waiting for the
        # next scheduled sweep - a best-effort first region sync (the same
        # real, live call "Refresh Regions" makes) so the newly-validated
        # account's region list, resource inventory, and dashboard populate
        # right away. Credentials are already proven valid by this point
        # (test_connection succeeded above), so a hiccup in this bonus step
        # must never fail the validate-credentials response itself.
        try:
            self.region_sync_service.sync_account(account_id, current_user_id)
        except Exception:
            pass
        # Phase 29: same best-effort, never-fail-the-response shape as the
        # region sync immediately above - kicks off real AWS resource
        # discovery (EC2/ECS/EKS/Lambda/RDS/S3/EBS/ELB/ASG/VPC/Subnets/
        # SecurityGroups/CloudWatch Alarms) right away, so the Dashboard
        # populates without the user needing to wait for the next scheduled
        # sweep or take any further action.
        try:
            self.discovery_service.discover_account(account_id, current_user_id)
        except Exception:
            pass
        return ConnectionTestResultRead(**result)

    def list_for_user(
        self, user_id: int, provider: str | None, page: int, page_size: int
    ) -> PaginatedResponse[CloudProviderAccountRead]:
        items, total = self.service.list_for_user(user_id, provider, page, page_size)
        total_pages = math.ceil(total / page_size) if page_size else 0
        return PaginatedResponse[CloudProviderAccountRead](
            items=[CloudProviderAccountRead.model_validate(i) for i in items],
            meta=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=total_pages
            ),
        )

    def get_own(self, account_id: int, current_user_id: int) -> CloudProviderAccountRead:
        return CloudProviderAccountRead.model_validate(
            self.service.get_own(account_id, current_user_id)
        )

    def update(
        self, account_id: int, current_user_id: int, payload: CloudProviderAccountUpdate
    ) -> CloudProviderAccountRead:
        return CloudProviderAccountRead.model_validate(
            self.service.update(account_id, current_user_id, payload)
        )

    def delete(self, account_id: int, current_user_id: int) -> None:
        self.service.delete(account_id, current_user_id)

    def list_linked_deployments(
        self, account_id: int, current_user_id: int
    ) -> list[CloudAccountDeploymentSummary]:
        pairs = self.service.list_linked_deployments(account_id, current_user_id)
        return [
            CloudAccountDeploymentSummary(
                deployment_id=deployment.id,
                deployment_name=deployment.name,
                namespace=deployment.namespace,
                cloud_resource_identifier=deployment.cloud_resource_identifier,
                latest_usage=ResourceUsageRead.model_validate(usage) if usage else None,
            )
            for deployment, usage in pairs
        ]

    def list_active_alerts(self, account_id: int, current_user_id: int) -> list[AlertRead]:
        alerts = self.service.list_active_alerts(account_id, current_user_id)
        return [AlertRead.model_validate(a) for a in alerts]

    def get_regions(self, account_id: int, current_user_id: int) -> CloudAccountRegionsRead:
        """Serves the account's stored region snapshot as-is, unless it's
        stale - either never synced yet (last_region_sync is null) or older
        than CLOUD_REGION_CACHE_TTL_HOURS (Phase 25E) - in which case one
        real, live discovery call is made first. This bounds how out of
        date a region list served here can ever be to one TTL window,
        without requiring a live provider call on every single read (that's
        what "Refresh Regions" bypasses this cache for)."""
        account = self.service.get_own(account_id, current_user_id)
        if self._is_region_cache_stale(account):
            result = self.region_sync_service.sync_account(account_id, current_user_id)
            account = result.account
        return _regions_read(account)

    @staticmethod
    def _is_region_cache_stale(account: CloudProviderAccount) -> bool:
        if account.last_region_sync is None:
            return True
        ttl = timedelta(hours=get_settings().CLOUD_REGION_CACHE_TTL_HOURS)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return now - account.last_region_sync > ttl

    def refresh_regions(self, account_id: int, current_user_id: int) -> CloudAccountRegionsRead:
        """Always bypasses whatever was previously stored and makes a real,
        live call to the provider - the "Refresh Regions" button's contract."""
        result = self.region_sync_service.sync_account(account_id, current_user_id)
        return _regions_read(result.account)

    def update_region(
        self, account_id: int, current_user_id: int, selected_region: str
    ) -> CloudProviderAccountRead:
        account = self.service.update_selected_region(account_id, current_user_id, selected_region)
        return CloudProviderAccountRead.model_validate(account)

    def list_inventory(
        self, account_id: int, current_user_id: int, category: str, region: str
    ) -> CloudResourceListRead:
        items = self.resource_inventory_service.list_resources(account_id, current_user_id, category, region)
        return CloudResourceListRead(category=category, region=region, items=list(items))

    def list_discovered_resources(
        self, account_id: int, current_user_id: int, resource_type: str | None, active_only: bool
    ) -> DiscoveredResourceListRead:
        pairs = self.discovery_service.list_resources(account_id, current_user_id, resource_type, active_only)
        return DiscoveredResourceListRead(
            items=[
                DiscoveredResourceRead(
                    id=resource.id,
                    resource_type=resource.resource_type,
                    external_id=resource.external_id,
                    name=resource.name,
                    region=resource.region,
                    availability_zone=resource.availability_zone,
                    status=resource.status,
                    instance_type=resource.instance_type,
                    public_ip=resource.public_ip,
                    private_ip=resource.private_ip,
                    is_active=resource.is_active,
                    first_seen_at=resource.first_seen_at,
                    last_seen_at=resource.last_seen_at,
                    latest_metric=Ec2MetricRead.model_validate(metric) if metric else None,
                )
                for resource, metric in pairs
            ]
        )

    def get_discovery_summary(self, account_id: int, current_user_id: int) -> CloudAccountDiscoverySummary:
        return CloudAccountDiscoverySummary(**self.discovery_service.get_summary(account_id, current_user_id))

    def discover_resources(self, account_id: int, current_user_id: int) -> CloudAccountDiscoverySummary:
        self.discovery_service.discover_account(account_id, current_user_id)
        return self.get_discovery_summary(account_id, current_user_id)

    def deploy_resource(
        self, account_id: int, current_user_id: int, resource_type: str, region: str, spec: dict
    ) -> CloudResourceRead:
        result = self.provisioning_service.deploy(account_id, current_user_id, resource_type, region, spec)
        return CloudResourceRead(**result)

    def destroy_resource(
        self,
        account_id: int,
        current_user_id: int,
        resource_type: str,
        resource_id: str,
        region: str,
        confirm: str,
    ) -> None:
        self.provisioning_service.destroy(
            account_id, current_user_id, resource_type, resource_id, region, confirm
        )
