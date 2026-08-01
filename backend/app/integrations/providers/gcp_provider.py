"""GCP CloudProviderClient adapter (Phase 25) - wraps the existing, already
real GCP fetcher function (app/integrations/gcp_monitoring.py) for
list_monitoring, and adds a genuinely new real call for list_regions via
`google-cloud-compute`'s RegionsClient - Compute Engine's own regions API,
never a hardcoded list. list_costs is deliberately NOT implemented (raises
the base class's "not yet supported" error) - unlike AWS/Azure, GCP has no
generalizable "spend by service" API callable with just account
credentials (see gcp_monitoring.py's own docstring for the same disclosed
limitation, carried forward here rather than worked around).
"""
import json

import tenacity
from google.api_core.exceptions import (
    DeadlineExceeded,
    GoogleAPICallError,
    PermissionDenied,
    ResourceExhausted,
    ServiceUnavailable,
    TooManyRequests,
    Unauthenticated,
)
from google.cloud import compute_v1, container_v1, storage
from google.oauth2 import service_account
from googleapiclient.discovery import build as build_google_api_client
from googleapiclient.errors import HttpError

from app.integrations.cloud_provider_client import (
    CloudProviderClient,
    CloudRegionInfo,
    CloudResourceSummary,
    ResourceUsageSnapshot,
)
from app.integrations.gcp_monitoring import fetch_instance_resource_usage
from app.integrations import region_metadata
from app.utils.exceptions import ValidationAppError

# The one, fixed, smallest/free-tier-eligible machine type deploy() will
# ever request - not user-configurable in this pass (see aws_provider.py's
# identical _DEPLOY_INSTANCE_TYPE for the same reasoning).
_DEPLOY_MACHINE_TYPE = "e2-micro"

# Compute Engine's Region resource has no dedicated human-readable display
# name field (unlike Azure's) - display_name/country/timezone come from the
# central app/integrations/region_metadata.py table (Phase 30), falling
# back to the raw region code for anything unmapped.


def _is_retryable_gcp_error(exc: BaseException) -> bool:
    if isinstance(exc, (ServiceUnavailable, DeadlineExceeded, TooManyRequests, ResourceExhausted)):
        return True
    # Cloud SQL (list_databases) goes through the generic googleapiclient
    # discovery client, not google-cloud-*, so it raises HttpError rather
    # than a google.api_core.exceptions subclass - same transient-status
    # codes, different exception type.
    if isinstance(exc, HttpError):
        return exc.resp.status in (429, 500, 503)
    return False


_gcp_retry = tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable_gcp_error),
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)


# Phase 25E: region-discovery error taxonomy (see aws_provider.py's
# identical rationale) - every category below is a real, distinct
# google.api_core.exceptions class GCP's own client library already raises.
def _classify_gcp_region_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, Unauthenticated):
        return "GCP_REGION_CREDENTIALS_REJECTED", f"GCP rejected the credentials: {exc}"
    if isinstance(exc, PermissionDenied):
        return "GCP_REGION_ACCESS_DENIED", f"GCP denied access to the region-discovery request: {exc}"
    if isinstance(exc, (TooManyRequests, ResourceExhausted)):
        return "GCP_REGION_THROTTLED", f"GCP throttled the region-discovery request even after retries: {exc}"
    if isinstance(exc, ServiceUnavailable):
        return "GCP_REGION_PROVIDER_OUTAGE", f"GCP reported a service outage: {exc}"
    if isinstance(exc, DeadlineExceeded):
        return "GCP_REGION_TIMEOUT", f"Timed out reaching GCP to discover regions: {exc}"
    return "GCP_REGION_DISCOVERY_FAILED", f"GCP rejected the region-discovery request: {exc}"


class GcpCloudProviderClient(CloudProviderClient):
    @property
    def provider_name(self) -> str:
        return "gcp"

    def _load_credentials(self) -> tuple[service_account.Credentials, str]:
        service_account_json = self.credentials.get("service_account_json")
        if not service_account_json:
            raise ValidationAppError(
                "GCP credentials must include 'service_account_json' (the full service "
                "account key JSON, as a string)",
                code="GCP_CREDENTIALS_INCOMPLETE",
            )
        try:
            service_account_info = json.loads(service_account_json)
        except (TypeError, ValueError) as exc:
            raise ValidationAppError(
                "GCP credentials 'service_account_json' is not valid JSON",
                code="GCP_CREDENTIALS_INCOMPLETE",
            ) from exc

        project_id = self.credentials.get("project_id") or service_account_info.get("project_id")
        if not project_id:
            raise ValidationAppError(
                "GCP credentials must include 'project_id' (or a service_account_json "
                "that itself contains one)",
                code="GCP_CREDENTIALS_INCOMPLETE",
            )
        return service_account.Credentials.from_service_account_info(service_account_info), project_id

    def authenticate(self) -> None:
        self._load_credentials()

    def list_regions(self) -> list[CloudRegionInfo]:
        google_credentials, project_id = self._load_credentials()
        client = compute_v1.RegionsClient(credentials=google_credentials)

        @_gcp_retry
        def _list_regions():
            return list(client.list(project=project_id))

        try:
            regions = _list_regions()
        except GoogleAPICallError as exc:
            code, message = _classify_gcp_region_error(exc)
            raise ValidationAppError(message, code=code) from exc

        results = []
        for region in regions:
            metadata = region_metadata.lookup("gcp", region.name)
            results.append(
                {
                    "id": region.name,
                    "display_name": metadata["display_name"] if metadata else region.name,
                    "country": metadata["country"] if metadata else None,
                    "timezone": metadata["timezone"] if metadata else None,
                }
            )
        if not results:
            raise ValidationAppError(
                "GCP returned zero regions for this project - unexpected for a working project, "
                "and treated as a failure rather than a legitimately empty result",
                code="GCP_REGION_NO_REGIONS_RETURNED",
            )
        return results

    def list_projects(self) -> list[str]:
        _, project_id = self._load_credentials()
        return [project_id]

    def _identity(self) -> tuple[str | None, str | None, str | None]:
        # Best-effort only - the base class's test_connection() has already
        # proven the credentials work via a real list_regions() call by the
        # time this runs. No cheap, reliably-enabled API gives a friendlier
        # "account alias" than the project id itself, so that's left None
        # rather than an extra fragile call - the service account's own
        # email is a real, always-available "principal" equivalent.
        service_account_json = self.credentials.get("service_account_json")
        principal = None
        if service_account_json:
            try:
                principal = json.loads(service_account_json).get("client_email")
            except (TypeError, ValueError):
                principal = None
        _, project_id = self._load_credentials()
        return project_id, None, principal

    def list_monitoring(self, resource_id: str, lookback_minutes: int) -> ResourceUsageSnapshot:
        return fetch_instance_resource_usage(self.credentials, self.region, resource_id, lookback_minutes)  # type: ignore[return-value]

    def list_resources(self, region: str) -> list[CloudResourceSummary]:
        google_credentials, project_id = self._load_credentials()
        client = compute_v1.InstancesClient(credentials=google_credentials)

        @_gcp_retry
        def _aggregated_list():
            # Compute Engine instances are zone-scoped (e.g. "us-central1-a"),
            # not region-scoped - aggregated_list() is the real API's own
            # way of listing across every zone, filtered here to the zones
            # that belong to the requested region.
            return list(client.aggregated_list(project=project_id))

        try:
            aggregated = _aggregated_list()
            results: list[CloudResourceSummary] = []
            for zone, scoped_list in aggregated:
                zone_name = zone.split("/")[-1]
                if not zone_name.startswith(f"{region}-"):
                    continue
                for instance in scoped_list.instances or []:
                    results.append(
                        {
                            "id": str(instance.id),
                            "name": instance.name,
                            "type": instance.machine_type.split("/")[-1] if instance.machine_type else "unknown",
                            "region": region,
                            "status": instance.status or "unknown",
                            "created_at": None,
                        }
                    )
            return results
        except (PermissionDenied, Unauthenticated) as exc:
            raise ValidationAppError(
                f"GCP rejected the credentials: {exc}", code="GCP_RESOURCE_INVENTORY_FAILED"
            ) from exc
        except GoogleAPICallError as exc:
            raise ValidationAppError(
                f"GCP rejected the resource-inventory request: {exc}", code="GCP_RESOURCE_INVENTORY_FAILED"
            ) from exc

    def list_clusters(self, region: str) -> list[CloudResourceSummary]:
        google_credentials, project_id = self._load_credentials()
        client = container_v1.ClusterManagerClient(credentials=google_credentials)

        @_gcp_retry
        def _list_clusters():
            return client.list_clusters(parent=f"projects/{project_id}/locations/-")

        try:
            response = _list_clusters()
            return [
                {
                    "id": cluster.name,
                    "name": cluster.name,
                    "type": "gke",
                    "region": region,
                    "status": cluster.status.name if cluster.status else "unknown",
                    "created_at": None,
                }
                for cluster in response.clusters
                if cluster.location == region or cluster.zone.startswith(f"{region}-")
            ]
        except (PermissionDenied, Unauthenticated) as exc:
            raise ValidationAppError(
                f"GCP rejected the credentials: {exc}", code="GCP_CLUSTER_INVENTORY_FAILED"
            ) from exc
        except GoogleAPICallError as exc:
            raise ValidationAppError(
                f"GCP rejected the cluster-inventory request: {exc}", code="GCP_CLUSTER_INVENTORY_FAILED"
            ) from exc

    def list_databases(self, region: str) -> list[CloudResourceSummary]:
        # Cloud SQL has no dedicated google-cloud-* client library - the
        # real, official way to call it is the generic googleapiclient
        # discovery-based sqladmin API, same as GCP's own gcloud CLI uses
        # under the hood.
        google_credentials, project_id = self._load_credentials()

        @_gcp_retry
        def _list_instances():
            service = build_google_api_client("sqladmin", "v1beta4", credentials=google_credentials)
            return service.instances().list(project=project_id).execute()

        try:
            response = _list_instances()
            return [
                {
                    "id": instance["name"],
                    "name": instance["name"],
                    "type": instance.get("databaseVersion", "unknown"),
                    "region": region,
                    "status": instance.get("state", "unknown"),
                    "created_at": None,
                }
                for instance in response.get("items", [])
                if instance.get("region") == region
            ]
        except HttpError as exc:
            raise ValidationAppError(
                f"GCP rejected the database-inventory request: {exc}", code="GCP_DATABASE_INVENTORY_FAILED"
            ) from exc

    def list_storage(self, region: str) -> list[CloudResourceSummary]:
        google_credentials, project_id = self._load_credentials()

        @_gcp_retry
        def _list_buckets():
            client = storage.Client(credentials=google_credentials, project=project_id)
            return list(client.list_buckets())

        try:
            buckets = _list_buckets()
            return [
                {
                    "id": bucket.name,
                    "name": bucket.name,
                    "type": "gcs_bucket",
                    "region": region,
                    "status": "available",
                    "created_at": bucket.time_created,
                }
                for bucket in buckets
                if (bucket.location or "").lower() == region.lower()
            ]
        except GoogleAPICallError as exc:
            raise ValidationAppError(
                f"GCP rejected the storage-inventory request: {exc}", code="GCP_STORAGE_INVENTORY_FAILED"
            ) from exc

    def list_networking(self, region: str) -> list[CloudResourceSummary]:
        # VPC networks are global resources in GCP, not region-scoped - the
        # same result is returned regardless of which region is requested,
        # disclosed honestly rather than fabricating a per-region filter
        # the real API has no concept of (same stance as aws_provider.py's
        # S3 disclosure).
        google_credentials, project_id = self._load_credentials()
        client = compute_v1.NetworksClient(credentials=google_credentials)

        @_gcp_retry
        def _list_networks():
            return list(client.list(project=project_id))

        try:
            networks = _list_networks()
            return [
                {
                    "id": str(network.id),
                    "name": network.name,
                    "type": "vpc_network",
                    "region": region,
                    "status": "available",
                    "created_at": None,
                }
                for network in networks
            ]
        except (PermissionDenied, Unauthenticated) as exc:
            raise ValidationAppError(
                f"GCP rejected the credentials: {exc}", code="GCP_NETWORKING_INVENTORY_FAILED"
            ) from exc
        except GoogleAPICallError as exc:
            raise ValidationAppError(
                f"GCP rejected the networking-inventory request: {exc}", code="GCP_NETWORKING_INVENTORY_FAILED"
            ) from exc

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
            return self._destroy_compute(region, resource_id, resource_id)
        if resource_type == "storage":
            return self._destroy_storage(resource_id)
        if resource_type == "networking":
            return self._destroy_networking(resource_id)
        raise self._not_yet_supported(f"Provisioning of '{resource_type}'")

    def _deploy_compute(self, region: str, spec: dict) -> CloudResourceSummary:
        image = spec.get("image")
        if not image:
            raise ValidationAppError(
                "GCP compute deploy requires spec.image (a full image resource path, e.g. "
                "'projects/debian-cloud/global/images/family/debian-12')",
                code="GCP_DEPLOY_SPEC_INCOMPLETE",
            )
        google_credentials, project_id = self._load_credentials()
        zone = spec.get("zone", f"{region}-a")
        name = spec.get("name", "cloud-ai-platform-instance")

        instance = compute_v1.Instance(
            name=name,
            machine_type=f"zones/{zone}/machineTypes/{_DEPLOY_MACHINE_TYPE}",
            disks=[
                compute_v1.AttachedDisk(
                    boot=True,
                    auto_delete=True,
                    initialize_params=compute_v1.AttachedDiskInitializeParams(source_image=image),
                )
            ],
            network_interfaces=[compute_v1.NetworkInterface(network=spec.get("network", "global/networks/default"))],
        )
        client = compute_v1.InstancesClient(credentials=google_credentials)
        try:
            operation = client.insert(project=project_id, zone=zone, instance_resource=instance)
            operation.result()
        except (PermissionDenied, Unauthenticated) as exc:
            raise ValidationAppError(f"GCP rejected the credentials: {exc}", code="GCP_DEPLOY_FAILED") from exc
        except GoogleAPICallError as exc:
            raise ValidationAppError(f"GCP rejected the deploy request: {exc}", code="GCP_DEPLOY_FAILED") from exc

        return {
            "id": name,
            "name": name,
            "type": _DEPLOY_MACHINE_TYPE,
            "region": region,
            "status": "provisioning",
            "created_at": None,
        }

    def _destroy_compute(self, region: str, zone_hint: str, resource_id: str) -> None:
        google_credentials, project_id = self._load_credentials()
        # Compute instances are deleted by name within a zone, not region -
        # the caller only has the region, so this assumes the same
        # "{region}-a" default zone deploy() used (a real limitation:
        # an instance created in a non-default zone within this region
        # needs its zone tracked separately to be destroyed this way).
        zone = f"{region}-a"
        client = compute_v1.InstancesClient(credentials=google_credentials)
        try:
            operation = client.delete(project=project_id, zone=zone, instance=resource_id)
            operation.result()
        except (PermissionDenied, Unauthenticated) as exc:
            raise ValidationAppError(f"GCP rejected the credentials: {exc}", code="GCP_DESTROY_FAILED") from exc
        except GoogleAPICallError as exc:
            raise ValidationAppError(f"GCP rejected the destroy request: {exc}", code="GCP_DESTROY_FAILED") from exc

    def _deploy_storage(self, region: str, spec: dict) -> CloudResourceSummary:
        name = spec.get("name")
        if not name:
            raise ValidationAppError(
                "GCP storage deploy requires spec.name (a globally-unique GCS bucket name)",
                code="GCP_DEPLOY_SPEC_INCOMPLETE",
            )
        google_credentials, project_id = self._load_credentials()
        try:
            client = storage.Client(credentials=google_credentials, project=project_id)
            client.create_bucket(name, location=region)
        except GoogleAPICallError as exc:
            raise ValidationAppError(f"GCP rejected the deploy request: {exc}", code="GCP_DEPLOY_FAILED") from exc

        return {"id": name, "name": name, "type": "gcs_bucket", "region": region, "status": "available", "created_at": None}

    def _destroy_storage(self, resource_id: str) -> None:
        google_credentials, project_id = self._load_credentials()
        try:
            client = storage.Client(credentials=google_credentials, project=project_id)
            # Requires an already-empty bucket - a real GCS precondition
            # this platform does not attempt to bypass by force-emptying it.
            client.bucket(resource_id).delete()
        except GoogleAPICallError as exc:
            raise ValidationAppError(f"GCP rejected the destroy request: {exc}", code="GCP_DESTROY_FAILED") from exc

    def _deploy_networking(self, region: str, spec: dict) -> CloudResourceSummary:
        google_credentials, project_id = self._load_credentials()
        name = spec.get("name", "cloud-ai-platform-network")
        network = compute_v1.Network(name=name, auto_create_subnetworks=spec.get("auto_create_subnetworks", True))
        client = compute_v1.NetworksClient(credentials=google_credentials)
        try:
            operation = client.insert(project=project_id, network_resource=network)
            operation.result()
        except (PermissionDenied, Unauthenticated) as exc:
            raise ValidationAppError(f"GCP rejected the credentials: {exc}", code="GCP_DEPLOY_FAILED") from exc
        except GoogleAPICallError as exc:
            raise ValidationAppError(f"GCP rejected the deploy request: {exc}", code="GCP_DEPLOY_FAILED") from exc

        return {
            "id": name,
            "name": name,
            "type": "vpc_network",
            "region": region,
            "status": "available",
            "created_at": None,
        }

    def _destroy_networking(self, resource_id: str) -> None:
        google_credentials, project_id = self._load_credentials()
        client = compute_v1.NetworksClient(credentials=google_credentials)
        try:
            operation = client.delete(project=project_id, network=resource_id)
            operation.result()
        except (PermissionDenied, Unauthenticated) as exc:
            raise ValidationAppError(f"GCP rejected the credentials: {exc}", code="GCP_DESTROY_FAILED") from exc
        except GoogleAPICallError as exc:
            raise ValidationAppError(f"GCP rejected the destroy request: {exc}", code="GCP_DESTROY_FAILED") from exc
