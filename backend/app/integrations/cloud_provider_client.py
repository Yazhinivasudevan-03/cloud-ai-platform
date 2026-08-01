"""CloudProviderClient: the provider-agnostic interface every cloud
integration in this platform implements (Phase 25). This is the
generalization of the pattern `app/services/cloud_sync_service.py`'s
`_PROVIDER_FETCHERS` dict already proved out for real-time metrics alone -
one typed interface covering region discovery, resource inventory, cost,
monitoring, and provisioning, so that a controller/service never branches
on `if provider == "aws"` anywhere; it only ever calls through this
interface, obtained from `app/integrations/provider_factory.py`.

Not every method is implemented by every provider in every sub-phase of
Phase 25 (see docs/PHASE_25.md). A method that isn't implemented yet for a
given provider raises a clear `ValidationAppError` naming exactly what's
missing, rather than silently returning an empty/fabricated result - the
same "disclose, don't fake" stance this project has taken since
aws_cloudwatch.py's very first honest memory/disk limitation.
"""
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import TypedDict

from app.utils.exceptions import ValidationAppError


class CloudRegionInfo(TypedDict):
    id: str
    display_name: str


class CloudResourceSummary(TypedDict):
    """Normalized shape for every list_resources/list_clusters/
    list_databases/list_storage/list_networking result (Phase 25C) -
    provider-specific fields that don't fit this shape are simply omitted,
    never invented."""

    id: str
    name: str
    type: str
    region: str
    status: str
    created_at: datetime | None


class ResourceUsageSnapshot(TypedDict):
    cpu_usage_percent: float
    memory_usage_mb: float
    disk_usage_mb: float
    network_in_kbps: float
    network_out_kbps: float
    recorded_at: datetime


class MonthlyServiceCost(TypedDict):
    service_name: str
    cost_amount: float
    currency: str
    billing_period_start: date
    billing_period_end: date


class ConnectionTestResult(TypedDict):
    """Returned by test_connection() - a real, live proof that a credential
    pair actually works, used both by the pre-save "Test Connection" button
    and by the post-save validate-credentials call that flips
    CloudProviderAccount.credentials_validated. account_alias/principal are
    best-effort identity details (e.g. AWS IAM account alias/ARN) - None,
    never fabricated, when the provider has no cheap way to supply one."""

    provider: str
    account_id: str | None
    account_alias: str | None
    principal: str | None
    region: str
    status: str


class CloudProviderClient(ABC):
    """One instance is scoped to a single CloudProviderAccount's decrypted
    credentials + currently selected region, mirroring how every existing
    fetcher function already takes `(credentials, region, ...)` per call."""

    def __init__(self, credentials: dict[str, str], region: str):
        self.credentials = credentials
        self.region = region

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """e.g. 'aws', 'azure', 'gcp', 'oci', 'alibaba' - used only for
        error messages and the provider_factory registry key, never for
        conditional branching inside shared service/controller code."""

    def _not_yet_supported(self, capability: str) -> ValidationAppError:
        return ValidationAppError(
            f"{capability} is not yet supported for provider '{self.provider_name}'",
            code=f"{capability.upper().replace(' ', '_')}_NOT_YET_SUPPORTED",
        )

    def authenticate(self) -> None:
        """Validates that the stored credentials are at least well-formed
        enough to attempt a real call (e.g. required keys present) -
        actual validity is only ever proven by a real provider API call,
        never assumed. Default no-op; providers with real credential-shape
        checks override this to raise ValidationAppError early."""

    def disconnect(self) -> None:
        """This platform holds no persistent session/token to revoke - every
        real call authenticates fresh from the stored encrypted credentials
        (see app/utils/crypto.py), so there is nothing to disconnect here.
        Removing an account entirely is CloudProviderAccountService.delete()."""

    @abstractmethod
    def list_regions(self) -> list[CloudRegionInfo]:
        """Real, live call to the provider's own region-listing API - never
        a hardcoded list. Raises ValidationAppError on missing credentials
        or a rejected request."""

    def refresh_regions(self) -> list[CloudRegionInfo]:
        """Force a live re-fetch, bypassing any cache the caller may keep -
        at this layer that's identical to list_regions(); caching itself
        lives one layer up, in CloudRegionSyncService / the database."""
        return self.list_regions()

    def list_projects(self) -> list[str]:
        raise self._not_yet_supported("Project listing")

    def list_resources(self, region: str) -> list[CloudResourceSummary]:
        raise self._not_yet_supported("Resource inventory")

    def list_clusters(self, region: str) -> list[CloudResourceSummary]:
        raise self._not_yet_supported("Cluster inventory")

    def list_databases(self, region: str) -> list[CloudResourceSummary]:
        raise self._not_yet_supported("Database inventory")

    def list_storage(self, region: str) -> list[CloudResourceSummary]:
        raise self._not_yet_supported("Storage inventory")

    def list_networking(self, region: str) -> list[CloudResourceSummary]:
        raise self._not_yet_supported("Networking inventory")

    # --- Phase 29: broader automatic-discovery inventory categories ---
    # Same "raises _not_yet_supported by default" shape as the 5 methods
    # above (Phase 25C) - a provider that hasn't implemented one of these
    # yet honestly discloses that rather than returning a fabricated empty
    # list. AWS implements all 8 for real (see
    # app/integrations/providers/aws_provider.py); every other provider is
    # unaffected by adding these.
    def list_ecs_clusters(self, region: str) -> list[CloudResourceSummary]:
        raise self._not_yet_supported("ECS cluster inventory")

    def list_serverless_functions(self, region: str) -> list[CloudResourceSummary]:
        raise self._not_yet_supported("Serverless function inventory")

    def list_volumes(self, region: str) -> list[CloudResourceSummary]:
        raise self._not_yet_supported("Volume inventory")

    def list_load_balancers(self, region: str) -> list[CloudResourceSummary]:
        raise self._not_yet_supported("Load balancer inventory")

    def list_scaling_groups(self, region: str) -> list[CloudResourceSummary]:
        raise self._not_yet_supported("Scaling group inventory")

    def list_subnets(self, region: str) -> list[CloudResourceSummary]:
        raise self._not_yet_supported("Subnet inventory")

    def list_security_groups(self, region: str) -> list[CloudResourceSummary]:
        raise self._not_yet_supported("Security group inventory")

    def list_alarms(self, region: str) -> list[CloudResourceSummary]:
        raise self._not_yet_supported("Alarm inventory")

    def list_ec2_instances_detailed(self, region: str) -> list[dict]:
        """Richer EC2 instance detail for the automatic-discovery/dashboard
        pipeline (availability_zone, public_ip, private_ip, tags) - a
        superset of what list_resources()'s normalized CloudResourceSummary
        carries. Only meaningful for compute-instance-shaped providers;
        default disclosure matches every other optional method here."""
        raise self._not_yet_supported("Detailed instance inventory")

    def list_monitoring(self, resource_id: str, lookback_minutes: int) -> ResourceUsageSnapshot:
        raise self._not_yet_supported("Monitoring")

    def list_costs(self, months: int) -> list[MonthlyServiceCost]:
        raise self._not_yet_supported("Cost sync")

    def deploy(self, region: str, resource_type: str, spec: dict) -> CloudResourceSummary:
        raise self._not_yet_supported("Provisioning")

    def destroy(self, region: str, resource_type: str, resource_id: str) -> None:
        raise self._not_yet_supported("Provisioning")

    def test_connection(self) -> ConnectionTestResult:
        """Real, live proof this credential pair works, used by the
        "Test Connection" button and the post-save validate-credentials
        call. The default implementation reuses list_regions() (already a
        real, classified-error network call per provider) as the
        connectivity proof, then validates the configured region is one of
        the ones actually discovered. AWS overrides this entirely with a
        dedicated STS GetCallerIdentity call (the specific mechanism
        requested for that provider); every other provider only overrides
        _identity() below to supply account_id/account_alias/principal
        alongside this same connectivity check."""
        regions = self.list_regions()
        region_ids = {r["id"] for r in regions}
        if self.region != "all" and self.region not in region_ids:
            raise ValidationAppError(
                f"'{self.region}' is not a recognized region for {self.provider_name} - use one of "
                f"{', '.join(sorted(region_ids))}",
                code=f"{self.provider_name.upper()}_REGION_INVALID",
            )
        account_id, account_alias, principal = self._identity()
        return {
            "provider": self.provider_name,
            "account_id": account_id,
            "account_alias": account_alias,
            "principal": principal,
            "region": self.region,
            "status": "success",
        }

    def _identity(self) -> tuple[str | None, str | None, str | None]:
        """(account_id, account_alias, principal) - best-effort identity
        details for the just-proven-working credentials. Returns all-None
        by default (honestly disclosed, never fabricated) for a provider
        that has no cheap way to supply one; overridden per provider below."""
        return None, None, None
