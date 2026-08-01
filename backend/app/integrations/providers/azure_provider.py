"""Azure CloudProviderClient adapter (Phase 25) - wraps the existing, already
real Azure fetcher functions (app/integrations/azure_monitor.py,
azure_cost_management.py) for list_monitoring/list_costs, and adds a
genuinely new real call for list_regions/list_projects via
`azure-mgmt-resource`'s SubscriptionClient - Azure Resource Manager's own
"Subscriptions -> List Locations" API, never a hardcoded list. Unlike AWS,
Azure's own API already returns a real human-readable `display_name` per
region, so no presentation-only lookup table is needed here.
"""
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError, ServiceRequestError
from azure.identity import ClientSecretCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.compute import models as compute_models
from azure.mgmt.containerservice import ContainerServiceClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.network import models as network_models
from azure.mgmt.resource import SubscriptionClient
from azure.mgmt.sql import SqlManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.storage import models as storage_models
import tenacity

from app.integrations.azure_cost_management import fetch_monthly_costs_by_service
from app.integrations.azure_monitor import fetch_vm_resource_usage
from app.integrations.cloud_provider_client import (
    CloudProviderClient,
    CloudRegionInfo,
    CloudResourceSummary,
    MonthlyServiceCost,
    ResourceUsageSnapshot,
)
from app.integrations import region_metadata
from app.utils.exceptions import ValidationAppError

# The one, fixed, smallest/free-tier-eligible VM size deploy() will ever
# request - not user-configurable in this pass (see aws_provider.py's
# identical _DEPLOY_INSTANCE_TYPE for the same reasoning).
_DEPLOY_VM_SIZE = "Standard_B1s"

_RETRYABLE_STATUS_CODES = {429, 500, 503}


def _is_retryable_azure_error(exc: BaseException) -> bool:
    if isinstance(exc, HttpResponseError):
        return exc.status_code in _RETRYABLE_STATUS_CODES
    return isinstance(exc, ServiceRequestError)


_azure_retry = tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable_azure_error),
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)

# Phase 25E: region-discovery error taxonomy (see aws_provider.py's
# identical rationale) - Azure's ClientAuthenticationError doesn't itself
# distinguish "expired" from "otherwise invalid" credentials, so both fold
# into CREDENTIALS_REJECTED rather than fabricating a distinction Azure's
# own SDK doesn't expose.
def _classify_azure_region_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, ClientAuthenticationError):
        return "AZURE_REGION_CREDENTIALS_REJECTED", f"Azure rejected the credentials: {exc}"
    if isinstance(exc, HttpResponseError):
        status = exc.status_code
        message = exc.message or str(exc)
        if status in (401, 403):
            return "AZURE_REGION_ACCESS_DENIED", f"Azure denied access to the region-discovery request: {message}"
        if status == 429:
            return "AZURE_REGION_THROTTLED", f"Azure throttled the region-discovery request even after retries: {message}"
        if status is not None and status >= 500:
            return "AZURE_REGION_PROVIDER_OUTAGE", f"Azure reported a service outage: {message}"
        return "AZURE_REGION_DISCOVERY_FAILED", f"Azure rejected the region-discovery request: {message}"
    # ServiceRequestError - Azure doesn't distinguish a slow connection
    # (timeout) from a fully unreachable one at this layer, so both are
    # disclosed honestly as one "network unreachable" category rather than
    # a fabricated split.
    return "AZURE_REGION_NETWORK_UNREACHABLE", f"Could not reach Azure to discover regions: {exc}"


class AzureCloudProviderClient(CloudProviderClient):
    @property
    def provider_name(self) -> str:
        return "azure"

    def authenticate(self) -> None:
        if not all(
            self.credentials.get(key) for key in ("tenant_id", "client_id", "client_secret", "subscription_id")
        ):
            raise ValidationAppError(
                "Azure credentials must include 'tenant_id', 'client_id', 'client_secret' "
                "and 'subscription_id'",
                code="AZURE_CREDENTIALS_INCOMPLETE",
            )

    def _credential(self) -> ClientSecretCredential:
        self.authenticate()
        return ClientSecretCredential(
            self.credentials["tenant_id"], self.credentials["client_id"], self.credentials["client_secret"]
        )

    def list_regions(self) -> list[CloudRegionInfo]:
        client = SubscriptionClient(self._credential())
        subscription_id = self.credentials["subscription_id"]

        @_azure_retry
        def _list_locations():
            return list(client.subscriptions.list_locations(subscription_id))

        try:
            locations = _list_locations()
        except (ClientAuthenticationError, HttpResponseError, ServiceRequestError) as exc:
            code, message = _classify_azure_region_error(exc)
            raise ValidationAppError(message, code=code) from exc

        regions = []
        for location in locations:
            metadata = region_metadata.lookup("azure", location.name)
            regions.append(
                {
                    "id": location.name,
                    "display_name": location.display_name or location.name,
                    "country": metadata["country"] if metadata else None,
                    "timezone": metadata["timezone"] if metadata else None,
                }
            )
        if not regions:
            raise ValidationAppError(
                "Azure returned zero locations for this subscription - unexpected for a working "
                "subscription, and treated as a failure rather than a legitimately empty result",
                code="AZURE_REGION_NO_REGIONS_RETURNED",
            )
        return regions

    def list_projects(self) -> list[str]:
        client = SubscriptionClient(self._credential())
        try:
            subscriptions = list(client.subscriptions.list())
        except ClientAuthenticationError as exc:
            raise ValidationAppError(
                f"Azure rejected the credentials: {exc}", code="AZURE_IDENTITY_REQUEST_FAILED"
            ) from exc
        except HttpResponseError as exc:
            raise ValidationAppError(
                f"Azure rejected the subscription-listing request: {exc.message or exc}",
                code="AZURE_IDENTITY_REQUEST_FAILED",
            ) from exc
        return [subscription.subscription_id for subscription in subscriptions]

    def _identity(self) -> tuple[str | None, str | None, str | None]:
        # Best-effort only - the base class's test_connection() has already
        # proven the credentials work via a real list_regions() call by the
        # time this runs; a failure to fetch the subscription's display
        # name here must never fail an otherwise-successful connection test.
        subscription_id = self.credentials.get("subscription_id")
        account_alias = None
        try:
            client = SubscriptionClient(self._credential())
            subscription = client.subscriptions.get(subscription_id)
            account_alias = subscription.display_name
        except (ClientAuthenticationError, HttpResponseError, ServiceRequestError):
            pass
        return subscription_id, account_alias, self.credentials.get("client_id")

    def list_monitoring(self, resource_id: str, lookback_minutes: int) -> ResourceUsageSnapshot:
        return fetch_vm_resource_usage(self.credentials, self.region, resource_id, lookback_minutes)  # type: ignore[return-value]

    def list_costs(self, months: int) -> list[MonthlyServiceCost]:
        return fetch_monthly_costs_by_service(self.credentials, months)

    def _subscription_id(self) -> str:
        self.authenticate()
        return self.credentials["subscription_id"]

    def _wrap_azure_error(self, exc: Exception, code: str) -> ValidationAppError:
        if isinstance(exc, ClientAuthenticationError):
            return ValidationAppError(f"Azure rejected the credentials: {exc}", code=code)
        if isinstance(exc, HttpResponseError):
            return ValidationAppError(f"Azure rejected the request: {exc.message or exc}", code=code)
        return ValidationAppError(f"Could not reach Azure: {exc}", code=code)

    @staticmethod
    def _matches_region(item_location: str | None, region: str) -> bool:
        return (item_location or "").replace(" ", "").lower() == region.replace(" ", "").lower()

    def list_resources(self, region: str) -> list[CloudResourceSummary]:
        client = ComputeManagementClient(self._credential(), self._subscription_id())

        @_azure_retry
        def _list_all():
            return list(client.virtual_machines.list_all())

        try:
            vms = _list_all()
        except (ClientAuthenticationError, HttpResponseError, ServiceRequestError) as exc:
            raise self._wrap_azure_error(exc, "AZURE_RESOURCE_INVENTORY_FAILED") from exc

        return [
            {
                "id": vm.id,
                "name": vm.name,
                "type": vm.hardware_profile.vm_size if vm.hardware_profile else "unknown",
                "region": region,
                "status": vm.provisioning_state or "unknown",
                "created_at": None,
            }
            for vm in vms
            if self._matches_region(vm.location, region)
        ]

    def list_clusters(self, region: str) -> list[CloudResourceSummary]:
        client = ContainerServiceClient(self._credential(), self._subscription_id())

        @_azure_retry
        def _list_clusters():
            return list(client.managed_clusters.list())

        try:
            clusters = _list_clusters()
        except (ClientAuthenticationError, HttpResponseError, ServiceRequestError) as exc:
            raise self._wrap_azure_error(exc, "AZURE_CLUSTER_INVENTORY_FAILED") from exc

        return [
            {
                "id": cluster.id,
                "name": cluster.name,
                "type": "aks",
                "region": region,
                "status": cluster.provisioning_state or "unknown",
                "created_at": None,
            }
            for cluster in clusters
            if self._matches_region(cluster.location, region)
        ]

    def list_databases(self, region: str) -> list[CloudResourceSummary]:
        client = SqlManagementClient(self._credential(), self._subscription_id())

        @_azure_retry
        def _list_servers():
            return list(client.servers.list())

        try:
            servers = _list_servers()
        except (ClientAuthenticationError, HttpResponseError, ServiceRequestError) as exc:
            raise self._wrap_azure_error(exc, "AZURE_DATABASE_INVENTORY_FAILED") from exc

        return [
            {
                "id": server.id,
                "name": server.name,
                "type": "azure_sql_server",
                "region": region,
                "status": server.state or "unknown",
                "created_at": None,
            }
            for server in servers
            if self._matches_region(server.location, region)
        ]

    def list_storage(self, region: str) -> list[CloudResourceSummary]:
        client = StorageManagementClient(self._credential(), self._subscription_id())

        @_azure_retry
        def _list_storage_accounts():
            return list(client.storage_accounts.list())

        try:
            accounts = _list_storage_accounts()
        except (ClientAuthenticationError, HttpResponseError, ServiceRequestError) as exc:
            raise self._wrap_azure_error(exc, "AZURE_STORAGE_INVENTORY_FAILED") from exc

        return [
            {
                "id": account.id,
                "name": account.name,
                "type": "storage_account",
                "region": region,
                "status": account.status_of_primary or account.provisioning_state or "unknown",
                "created_at": account.creation_time,
            }
            for account in accounts
            if self._matches_region(account.location, region)
        ]

    def list_networking(self, region: str) -> list[CloudResourceSummary]:
        client = NetworkManagementClient(self._credential(), self._subscription_id())

        @_azure_retry
        def _list_vnets():
            return list(client.virtual_networks.list_all())

        try:
            vnets = _list_vnets()
        except (ClientAuthenticationError, HttpResponseError, ServiceRequestError) as exc:
            raise self._wrap_azure_error(exc, "AZURE_NETWORKING_INVENTORY_FAILED") from exc

        return [
            {
                "id": vnet.id,
                "name": vnet.name,
                "type": "virtual_network",
                "region": region,
                "status": vnet.provisioning_state or "unknown",
                "created_at": None,
            }
            for vnet in vnets
            if self._matches_region(vnet.location, region)
        ]

    def deploy(self, region: str, resource_type: str, spec: dict) -> CloudResourceSummary:
        if resource_type == "compute":
            return self._deploy_compute(region, spec)
        if resource_type == "storage":
            return self._deploy_storage(region, spec)
        if resource_type == "networking":
            return self._deploy_networking(region, spec)
        raise self._not_yet_supported(f"Provisioning of '{resource_type}'")

    def destroy(self, region: str, resource_type: str, resource_id: str) -> None:
        if resource_type == "compute":
            return self._destroy_compute(resource_id)
        if resource_type == "storage":
            return self._destroy_storage(resource_id)
        if resource_type == "networking":
            return self._destroy_networking(resource_id)
        raise self._not_yet_supported(f"Provisioning of '{resource_type}'")

    @staticmethod
    def _require_spec(spec: dict, keys: tuple[str, ...]) -> None:
        missing = [k for k in keys if not spec.get(k)]
        if missing:
            raise ValidationAppError(
                f"Azure deploy requires spec.{', spec.'.join(missing)}", code="AZURE_DEPLOY_SPEC_INCOMPLETE"
            )

    def _deploy_compute(self, region: str, spec: dict) -> CloudResourceSummary:
        # A real Azure VM needs a resource group and a network interface
        # referencing an existing subnet - both real, standard Azure
        # prerequisites this platform cannot fabricate on the caller's
        # behalf (the same honest stance as requiring an AMI id for AWS).
        self._require_spec(spec, ("resource_group", "subnet_id", "admin_username", "admin_password"))
        resource_group = spec["resource_group"]
        name = spec.get("name", "cloud-ai-platform-vm")
        credential = self._credential()
        subscription_id = self._subscription_id()

        network_client = NetworkManagementClient(credential, subscription_id)
        nic_name = f"{name}-nic"
        try:
            nic_poller = network_client.network_interfaces.begin_create_or_update(
                resource_group,
                nic_name,
                network_models.NetworkInterface(
                    location=region,
                    ip_configurations=[
                        network_models.NetworkInterfaceIPConfiguration(
                            name="ipconfig1", subnet=network_models.Subnet(id=spec["subnet_id"])
                        )
                    ],
                ),
            )
            nic = nic_poller.result()

            compute_client = ComputeManagementClient(credential, subscription_id)
            image = spec.get(
                "image_reference",
                {"publisher": "Canonical", "offer": "0001-com-ubuntu-server-jammy", "sku": "22_04-lts", "version": "latest"},
            )
            vm_poller = compute_client.virtual_machines.begin_create_or_update(
                resource_group,
                name,
                compute_models.VirtualMachine(
                    location=region,
                    hardware_profile=compute_models.HardwareProfile(vm_size=_DEPLOY_VM_SIZE),
                    storage_profile=compute_models.StorageProfile(image_reference=compute_models.ImageReference(**image)),
                    os_profile=compute_models.OSProfile(
                        computer_name=name,
                        admin_username=spec["admin_username"],
                        admin_password=spec["admin_password"],
                    ),
                    network_profile=compute_models.NetworkProfile(
                        network_interfaces=[compute_models.NetworkInterfaceReference(id=nic.id, primary=True)]
                    ),
                ),
            )
            vm = vm_poller.result()
        except (ClientAuthenticationError, HttpResponseError, ServiceRequestError) as exc:
            raise self._wrap_azure_error(exc, "AZURE_DEPLOY_FAILED") from exc

        return {
            "id": vm.id,
            "name": vm.name,
            "type": _DEPLOY_VM_SIZE,
            "region": region,
            "status": vm.provisioning_state or "unknown",
            "created_at": None,
        }

    def _destroy_compute(self, resource_id: str) -> None:
        resource_group, vm_name = self._parse_resource_group_and_name(resource_id)
        client = ComputeManagementClient(self._credential(), self._subscription_id())
        try:
            client.virtual_machines.begin_delete(resource_group, vm_name).result()
        except (ClientAuthenticationError, HttpResponseError, ServiceRequestError) as exc:
            raise self._wrap_azure_error(exc, "AZURE_DESTROY_FAILED") from exc

    def _deploy_storage(self, region: str, spec: dict) -> CloudResourceSummary:
        self._require_spec(spec, ("resource_group", "name"))
        client = StorageManagementClient(self._credential(), self._subscription_id())
        name = spec["name"]
        try:
            poller = client.storage_accounts.begin_create(
                spec["resource_group"],
                name,
                storage_models.StorageAccountCreateParameters(
                    sku=storage_models.Sku(name="Standard_LRS"), kind="StorageV2", location=region
                ),
            )
            account = poller.result()
        except (ClientAuthenticationError, HttpResponseError, ServiceRequestError) as exc:
            raise self._wrap_azure_error(exc, "AZURE_DEPLOY_FAILED") from exc

        return {
            "id": account.id,
            "name": account.name,
            "type": "storage_account",
            "region": region,
            "status": account.provisioning_state or "unknown",
            "created_at": account.creation_time,
        }

    def _destroy_storage(self, resource_id: str) -> None:
        resource_group, account_name = self._parse_resource_group_and_name(resource_id)
        client = StorageManagementClient(self._credential(), self._subscription_id())
        try:
            client.storage_accounts.delete(resource_group, account_name)
        except (ClientAuthenticationError, HttpResponseError, ServiceRequestError) as exc:
            raise self._wrap_azure_error(exc, "AZURE_DESTROY_FAILED") from exc

    def _deploy_networking(self, region: str, spec: dict) -> CloudResourceSummary:
        self._require_spec(spec, ("resource_group",))
        name = spec.get("name", "cloud-ai-platform-vnet")
        cidr_block = spec.get("cidr_block", "10.0.0.0/16")
        client = NetworkManagementClient(self._credential(), self._subscription_id())
        try:
            poller = client.virtual_networks.begin_create_or_update(
                spec["resource_group"],
                name,
                network_models.VirtualNetwork(
                    location=region, address_space=network_models.AddressSpace(address_prefixes=[cidr_block])
                ),
            )
            vnet = poller.result()
        except (ClientAuthenticationError, HttpResponseError, ServiceRequestError) as exc:
            raise self._wrap_azure_error(exc, "AZURE_DEPLOY_FAILED") from exc

        return {
            "id": vnet.id,
            "name": vnet.name,
            "type": "virtual_network",
            "region": region,
            "status": vnet.provisioning_state or "unknown",
            "created_at": None,
        }

    def _destroy_networking(self, resource_id: str) -> None:
        resource_group, vnet_name = self._parse_resource_group_and_name(resource_id)
        client = NetworkManagementClient(self._credential(), self._subscription_id())
        try:
            client.virtual_networks.begin_delete(resource_group, vnet_name).result()
        except (ClientAuthenticationError, HttpResponseError, ServiceRequestError) as exc:
            raise self._wrap_azure_error(exc, "AZURE_DESTROY_FAILED") from exc

    @staticmethod
    def _parse_resource_group_and_name(resource_id: str) -> tuple[str, str]:
        # Azure resource IDs are always
        # /subscriptions/{sub}/resourceGroups/{rg}/providers/.../{name} -
        # destroy() only receives the id (as returned by deploy()/list_*()),
        # so the resource group is recovered from it rather than requiring
        # the caller to pass it separately again.
        parts = resource_id.strip("/").split("/")
        try:
            rg_index = parts.index("resourceGroups")
            return parts[rg_index + 1], parts[-1]
        except (ValueError, IndexError) as exc:
            raise ValidationAppError(
                f"'{resource_id}' is not a recognizable Azure resource ID", code="AZURE_DESTROY_FAILED"
            ) from exc
