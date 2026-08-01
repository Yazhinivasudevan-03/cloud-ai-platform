"""Business logic for Phase 29's automatic AWS resource discovery: the
missing bridge between "a cloud account is connected" and "the platform
actually knows what real resources exist in it" - see docs/PHASE_29.md for
the full root-cause writeup. Mirrors CloudRegionSyncService's/
CloudSyncService's established shape closely (per-account try/except
tolerance in the "sync everything" path, a real call in the single-account
path that raises so the caller sees the exact error), and reuses
CloudResourceInventoryService's own region-resolution/"all regions"
aggregation convention rather than reinventing it.

Every real resource type this platform can discover (EC2 instances plus
the 12 other categories in CloudProviderClient) is upserted into
CloudResource, keyed by (account, type, region, external_id); anything
previously active that a fresh pass no longer observes is flipped
is_active=False (see CloudResourceRepository.mark_inactive_except) - the
generic mechanism behind new instances auto-appearing and
terminated/deleted ones auto-disappearing, with no reconnect required.

Real-time CloudWatch metrics collection (Phase 29's EC2-specific
requirement) rides the same discovery cycle: every active, running EC2
instance gets a fresh app.integrations.aws_cloudwatch.fetch_ec2_full_metrics
call and a new CloudResourceMetric row, so metrics refresh at exactly the
same cadence as inventory (CLOUD_RESOURCE_DISCOVERY_INTERVAL_SECONDS) -
no separate job needed.
"""
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.integrations.aws_cloudwatch import fetch_ec2_full_metrics
from app.integrations.cloud_provider_client import CloudProviderClient
from app.integrations.provider_factory import get_cloud_provider_client
from app.models.cloud_provider_account import CloudProviderAccount
from app.models.cloud_resource_metric import CloudResourceMetric
from app.repositories.cloud_provider_account_repository import CloudProviderAccountRepository
from app.repositories.cloud_resource_repository import CloudResourceRepository
from app.schemas.cloud_resource_discovery import ResourceDiscoverySummary
from app.services.cloud_region_sync_service import load_available_regions
from app.utils.crypto import decrypt_credentials
from app.utils.exceptions import ForbiddenError, NotFoundError, ValidationAppError
from app.utils.logger import get_logger

logger = get_logger("cloud_resource_discovery")

ALL_REGIONS_SENTINEL = "all"

EC2_RESOURCE_TYPE = "ec2_instance"

# Every category beyond EC2 goes through the generic CloudResourceSummary
# shape (id/name/type/region/status/created_at) via these plain
# CloudProviderClient method names - the same "one dict entry, no
# provider-name branching" registry pattern this project already uses
# throughout (see CloudResourceInventoryService._CATEGORY_METHODS,
# CloudSyncService._PROVIDER_FETCHERS).
_STANDARD_CATEGORY_METHODS: dict[str, str] = {
    "ecs_cluster": "list_ecs_clusters",
    "eks_cluster": "list_clusters",
    "lambda_function": "list_serverless_functions",
    "rds_database": "list_databases",
    "s3_bucket": "list_storage",
    "ebs_volume": "list_volumes",
    "load_balancer": "list_load_balancers",
    "auto_scaling_group": "list_scaling_groups",
    "vpc": "list_networking",
    "subnet": "list_subnets",
    "security_group": "list_security_groups",
    "cloudwatch_alarm": "list_alarms",
}


@dataclass
class DiscoveryResult:
    account: CloudProviderAccount
    resources_seen: int
    errors: list[str]


def _is_not_yet_supported(exc: ValidationAppError) -> bool:
    return (exc.code or "").endswith("_NOT_YET_SUPPORTED")


class CloudResourceDiscoveryService:
    def __init__(self, db: Session):
        self.db = db
        self.account_repository = CloudProviderAccountRepository(db)
        self.repository = CloudResourceRepository(db)

    def _get_account(self, account_id: int, current_user_id: int | None) -> CloudProviderAccount:
        account = self.account_repository.get_by_id(account_id)
        if account is None:
            raise NotFoundError(f"Cloud provider account {account_id} not found", code="CLOUD_ACCOUNT_NOT_FOUND")
        if current_user_id is not None and account.user_id != current_user_id:
            raise ForbiddenError(
                "Cannot access another user's cloud provider account", code="NOT_YOUR_CLOUD_ACCOUNT"
            )
        return account

    def discover_account(self, account_id: int, current_user_id: int | None = None) -> DiscoveryResult:
        account = self._get_account(account_id, current_user_id)
        credentials = decrypt_credentials(account.credentials_encrypted)
        regions = self._resolve_regions(account)
        seen_at = datetime.now(timezone.utc).replace(tzinfo=None)

        error_messages: list[str] = []
        total_seen = 0
        for region in regions:
            client = get_cloud_provider_client(account.provider, credentials, region)
            total_seen += self._discover_ec2(account, client, credentials, region, seen_at, error_messages)
            for resource_type, method_name in _STANDARD_CATEGORY_METHODS.items():
                total_seen += self._discover_standard_category(
                    account, client, region, resource_type, method_name, seen_at, error_messages
                )

        account.last_discovery_at = seen_at
        account.last_discovery_error = "; ".join(error_messages) if error_messages else None
        self.db.commit()

        logger.info(
            "Resource discovery for account %s (%s): %d resources seen across %d region(s), %d error(s)",
            account.id, account.provider, total_seen, len(regions), len(error_messages),
        )

        if error_messages:
            raise ValidationAppError(
                "; ".join(error_messages), code="CLOUD_RESOURCE_DISCOVERY_FAILED"
            )
        return DiscoveryResult(account=account, resources_seen=total_seen, errors=error_messages)

    def discover_all(self) -> ResourceDiscoverySummary:
        """Called by the scheduled job - discovers every connected,
        credentials-validated account, tolerating individual failures
        without aborting the rest (same filter/tolerance
        CloudRegionSyncService.sync_all_regions() already uses)."""
        accounts: list[CloudProviderAccount] = list(
            self.db.query(CloudProviderAccount)
            .filter(
                CloudProviderAccount.is_active.is_(True),
                CloudProviderAccount.credentials_validated.is_(True),
            )
            .all()
        )
        discovered = 0
        failed = 0
        for account in accounts:
            try:
                self.discover_account(account.id)
                discovered += 1
            except Exception:
                failed += 1
                logger.exception("Scheduled resource discovery failed for cloud account %s", account.id)
        return ResourceDiscoverySummary(
            accounts_attempted=len(accounts), accounts_discovered=discovered, accounts_failed=failed
        )

    def list_resources(
        self,
        account_id: int,
        current_user_id: int,
        resource_type: str | None = None,
        active_only: bool = True,
    ) -> list[tuple]:
        """Reads only from MySQL - no live provider call - which is what
        makes the Dashboard fast (requirement 5). Returns (resource, latest
        metric-or-None) pairs, joined here rather than requiring the caller
        to make a second round trip per resource."""
        self._get_account(account_id, current_user_id)
        resources = self.repository.list_for_account(account_id, resource_type, active_only)
        return [
            (
                resource,
                self.repository.get_latest_metric(resource.id) if resource.resource_type == EC2_RESOURCE_TYPE else None,
            )
            for resource in resources
        ]

    def get_summary(self, account_id: int, current_user_id: int) -> dict:
        account = self._get_account(account_id, current_user_id)
        resources = self.repository.list_for_account(account_id, active_only=True)
        instances = [r for r in resources if r.resource_type == EC2_RESOURCE_TYPE]
        counts_by_type: dict[str, int] = {}
        for resource in resources:
            counts_by_type[resource.resource_type] = counts_by_type.get(resource.resource_type, 0) + 1
        return {
            "total_instances": len(instances),
            "running_instances": sum(1 for r in instances if r.status == "running"),
            "stopped_instances": sum(1 for r in instances if r.status == "stopped"),
            "resource_counts_by_type": counts_by_type,
            "last_discovery_at": account.last_discovery_at,
            "last_discovery_error": account.last_discovery_error,
        }

    def _resolve_regions(self, account: CloudProviderAccount) -> list[str]:
        if account.region != ALL_REGIONS_SENTINEL:
            return [account.region]
        available_regions = load_available_regions(account)
        if not available_regions:
            raise ValidationAppError(
                "This account has no discovered regions yet - refresh regions before automatic "
                "resource discovery can run in 'all regions' mode",
                code="NO_REGIONS_DISCOVERED",
            )
        return [entry["id"] for entry in available_regions]

    def _discover_standard_category(
        self,
        account: CloudProviderAccount,
        client: CloudProviderClient,
        region: str,
        resource_type: str,
        method_name: str,
        seen_at: datetime,
        error_messages: list[str],
    ) -> int:
        method = getattr(client, method_name)
        logger.info(
            "Calling %s.%s region=%s account=%s", account.provider, method_name, region, account.id
        )
        try:
            items = method(region)
        except ValidationAppError as exc:
            if _is_not_yet_supported(exc):
                return 0
            logger.exception(
                "Discovery call failed: account=%s provider=%s region=%s category=%s",
                account.id, account.provider, region, resource_type,
            )
            error_messages.append(f"{resource_type} ({region}): {exc}")
            return 0

        seen_ids: set[int] = set()
        for item in items:
            resource = self.repository.upsert(
                user_id=account.user_id,
                cloud_provider_account_id=account.id,
                provider=account.provider,
                resource_type=resource_type,
                external_id=item["id"],
                name=item["name"],
                region=region,
                status=item["status"],
                seen_at=seen_at,
            )
            seen_ids.add(resource.id)
        self.repository.mark_inactive_except(account.id, resource_type, region, seen_ids)
        logger.info(
            "Discovered %d %s resource(s) for account %s region %s", len(items), resource_type, account.id, region
        )
        return len(items)

    def _discover_ec2(
        self,
        account: CloudProviderAccount,
        client: CloudProviderClient,
        credentials: dict[str, str],
        region: str,
        seen_at: datetime,
        error_messages: list[str],
    ) -> int:
        logger.info(
            "Calling %s.list_ec2_instances_detailed region=%s account=%s", account.provider, region, account.id
        )
        try:
            instances = client.list_ec2_instances_detailed(region)
        except ValidationAppError as exc:
            if _is_not_yet_supported(exc):
                return 0
            logger.exception(
                "Discovery call failed: account=%s provider=%s region=%s category=ec2_instance",
                account.id, account.provider, region,
            )
            error_messages.append(f"ec2_instance ({region}): {exc}")
            return 0

        seen_ids: set[int] = set()
        for item in instances:
            resource = self.repository.upsert(
                user_id=account.user_id,
                cloud_provider_account_id=account.id,
                provider=account.provider,
                resource_type=EC2_RESOURCE_TYPE,
                external_id=item["id"],
                name=item["name"],
                region=region,
                status=item["status"],
                availability_zone=item.get("availability_zone"),
                instance_type=item.get("instance_type"),
                public_ip=item.get("public_ip"),
                private_ip=item.get("private_ip"),
                tags_json=json.dumps(item.get("tags") or {}),
                seen_at=seen_at,
            )
            seen_ids.add(resource.id)
            if account.provider == "aws" and item.get("status") == "running":
                # Deliberately not folded into error_messages: the instance
                # itself was successfully discovered, and a momentary lack
                # of CloudWatch datapoints (e.g. right after the instance
                # started, before its first minute's metric has published)
                # is an expected, transient condition, not a discovery
                # failure - matches CloudSyncService.sync_all()'s existing
                # per-item tolerance for metric-fetch failures.
                self._collect_ec2_metrics(credentials, resource, item)
        self.repository.mark_inactive_except(account.id, EC2_RESOURCE_TYPE, region, seen_ids)
        logger.info("Discovered %d ec2_instance resource(s) for account %s region %s", len(instances), account.id, region)
        return len(instances)

    def _collect_ec2_metrics(self, credentials: dict[str, str], resource, item: dict) -> None:
        logger.info("Calling aws.cloudwatch.get_metric_data instance=%s region=%s", resource.external_id, resource.region)
        try:
            usage = fetch_ec2_full_metrics(
                credentials,
                resource.region,
                resource.external_id,
                item.get("instance_type", "unknown"),
                self._lookback_minutes(),
            )
        except ValidationAppError:
            logger.exception("CloudWatch metrics fetch failed for resource %s (%s)", resource.id, resource.external_id)
            return

        recorded_at = usage["recorded_at"]
        if recorded_at.tzinfo is not None:
            recorded_at = recorded_at.astimezone(timezone.utc).replace(tzinfo=None)
        self.repository.add_metric(
            CloudResourceMetric(
                cloud_resource_id=resource.id,
                cpu_usage_percent=usage["cpu_usage_percent"],
                network_in_kbps=usage["network_in_kbps"],
                network_out_kbps=usage["network_out_kbps"],
                disk_read_bytes=usage["disk_read_bytes"],
                disk_write_bytes=usage["disk_write_bytes"],
                status_check_failed=usage["status_check_failed"],
                memory_usage_mb=usage["memory_usage_mb"],
                recorded_at=recorded_at,
            )
        )

    @staticmethod
    def _lookback_minutes() -> int:
        return get_settings().CLOUD_SYNC_LOOKBACK_MINUTES
