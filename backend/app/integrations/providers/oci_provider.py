"""Oracle Cloud Infrastructure CloudProviderClient adapter (Phase 25B) -
the first genuinely new integration this project has ever had zero prior
code for (unlike AWS/Azure/GCP, which already had real monitoring/cost
fetchers from earlier phases this adapter could wrap). Built against the
official `oci` Python SDK's documented shapes.

Honesty note (matches this project's consistent stance elsewhere): there is
no OCI emulator available, and no live OCI tenancy to validate this against
(the same constraint Azure/GCP monitoring already disclosed - see
azure_monitor.py/gcp_monitoring.py's own docstrings). This module is
verified only against mocked `oci` SDK client responses (see
tests/test_oci_provider.py), never a real request/response round trip -
that is a real limitation of this pass, not something papered over.

Credentials dict shape (mirrors OCI's own config-file keys, since that's
the SDK's native format - see oci.config.validate_config): {"user":
"ocid1.user.oc1..<...>", "tenancy": "ocid1.tenancy.oc1..<...>",
"fingerprint": "<key fingerprint>", "key_content": "<PEM private key>",
"compartment_id": "ocid1.compartment.oc1..<...>" (defaults to the tenancy
OCID if omitted, same default OCI's own console uses for the root
compartment)}.

Only CPU utilization and network in/out are available from the standard
`oci_computeagent` metrics namespace without the OCI Management Agent
installed - memory/disk are reported as 0.0, the same disclosed limitation
as every other provider in this platform.
"""
from datetime import datetime, timedelta, timezone
from typing import TypedDict

import oci
import tenacity
from oci.exceptions import ServiceError

from app.integrations.cloud_provider_client import CloudProviderClient, CloudRegionInfo, CloudResourceSummary
from app.utils.exceptions import ValidationAppError

_REQUIRED_CREDENTIAL_KEYS = ("user", "tenancy", "fingerprint", "key_content")

# OCI's list_region_subscriptions() returns only region codes (e.g.
# "us-ashburn-1") and a subscription status, never a human display name -
# same presentation-only lookup pattern as aws_provider.py/gcp_provider.py,
# falling back to the raw region code for anything unmapped.
_OCI_REGION_DISPLAY_NAMES = {
    "us-ashburn-1": "US East (Ashburn)",
    "us-phoenix-1": "US West (Phoenix)",
    "uk-london-1": "UK South (London)",
    "eu-frankfurt-1": "Germany Central (Frankfurt)",
    "ap-mumbai-1": "India West (Mumbai)",
    "ap-tokyo-1": "Japan East (Tokyo)",
    "ap-singapore-1": "Singapore",
    "ap-sydney-1": "Australia East (Sydney)",
    "ca-toronto-1": "Canada Southeast (Toronto)",
    "sa-saopaulo-1": "Brazil East (Sao Paulo)",
}

_NAMESPACE = "oci_computeagent"

# The one, fixed, smallest/free-tier-eligible shape deploy() will ever
# request - not user-configurable in this pass (see aws_provider.py's
# identical _DEPLOY_INSTANCE_TYPE for the same reasoning).
_DEPLOY_SHAPE = "VM.Standard.E2.1.Micro"


class InstanceResourceUsage(TypedDict):
    cpu_usage_percent: float
    memory_usage_mb: float
    disk_usage_mb: float
    network_in_kbps: float
    network_out_kbps: float
    recorded_at: datetime


def _is_retryable_oci_error(exc: BaseException) -> bool:
    if isinstance(exc, ServiceError):
        return exc.status in (429, 500, 503) or exc.code in ("TooManyRequests", "InternalError")
    return False


_oci_retry = tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable_oci_error),
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)


# Phase 25E: region-discovery error taxonomy (see aws_provider.py's
# identical rationale) - OCI's ServiceError already exposes a real HTTP
# status per failure, so the categories below are read directly from it,
# never guessed.
def _classify_oci_region_error(exc: ServiceError) -> tuple[str, str]:
    message = f"OCI rejected the region-discovery request ({exc.code}): {exc.message}"
    if exc.status == 401:
        return "OCI_REGION_CREDENTIALS_REJECTED", f"OCI rejected the credentials ({exc.code}): {exc.message}"
    if exc.status == 403:
        return "OCI_REGION_ACCESS_DENIED", message
    if exc.status == 429:
        return "OCI_REGION_THROTTLED", f"OCI throttled the region-discovery request even after retries: {exc.message}"
    if exc.status >= 500:
        return "OCI_REGION_PROVIDER_OUTAGE", f"OCI reported a service outage: {exc.message}"
    return "OCI_REGION_DISCOVERY_FAILED", message


class OciCloudProviderClient(CloudProviderClient):
    @property
    def provider_name(self) -> str:
        return "oci"

    def authenticate(self) -> None:
        missing = [key for key in _REQUIRED_CREDENTIAL_KEYS if not self.credentials.get(key)]
        if missing:
            raise ValidationAppError(
                f"OCI credentials must include {', '.join(_REQUIRED_CREDENTIAL_KEYS)} "
                f"(missing: {', '.join(missing)})",
                code="OCI_CREDENTIALS_INCOMPLETE",
            )

    def _config(self) -> dict:
        self.authenticate()
        return {
            "user": self.credentials["user"],
            "tenancy": self.credentials["tenancy"],
            "fingerprint": self.credentials["fingerprint"],
            "key_content": self.credentials["key_content"],
            "region": self.region if self.region and self.region != "all" else "us-ashburn-1",
        }

    def _compartment_id(self) -> str:
        # A compartment_id is required by most OCI calls; the tenancy OCID
        # itself is a valid compartment_id (the root compartment) when the
        # caller hasn't configured a more specific one, matching what OCI's
        # own console defaults new resources into.
        return self.credentials.get("compartment_id") or self.credentials["tenancy"]

    def list_regions(self) -> list[CloudRegionInfo]:
        config = self._config()
        client = oci.identity.IdentityClient(config)

        @_oci_retry
        def _list_region_subscriptions():
            return client.list_region_subscriptions(config["tenancy"])

        try:
            response = _list_region_subscriptions()
        except ServiceError as exc:
            code, message = _classify_oci_region_error(exc)
            raise ValidationAppError(message, code=code) from exc

        regions = [
            {
                "id": subscription.region_name,
                "display_name": _OCI_REGION_DISPLAY_NAMES.get(subscription.region_name, subscription.region_name),
            }
            for subscription in response.data
            # "READY" is the only status that means the region is actually
            # usable - a subscription still being provisioned isn't a real
            # choice yet, so it's excluded rather than shown as available.
            if getattr(subscription, "status", "READY") == "READY"
        ]
        if not regions:
            raise ValidationAppError(
                "OCI returned zero ready region subscriptions for this tenancy - unexpected for a "
                "working tenancy, and treated as a failure rather than a legitimately empty result",
                code="OCI_REGION_NO_REGIONS_RETURNED",
            )
        return regions

    def _identity(self) -> tuple[str | None, str | None, str | None]:
        # Best-effort only - the base class's test_connection() has already
        # proven the credentials work via a real list_regions() call by the
        # time this runs; a failure to fetch the tenancy's display name here
        # must never fail an otherwise-successful connection test.
        tenancy_id = self.credentials.get("tenancy")
        account_alias = None
        try:
            client = oci.identity.IdentityClient(self._config())
            account_alias = client.get_tenancy(tenancy_id).data.name
        except ServiceError:
            pass
        return tenancy_id, account_alias, self.credentials.get("user")

    def list_monitoring(self, resource_id: str, lookback_minutes: int) -> InstanceResourceUsage:
        """Queries real OCI Monitoring (via MQL) for a single Compute
        instance's CPU/network over the last `lookback_minutes`. `resource_id`
        is the instance's OCID - the same value the deployment's
        cloud_resource_identifier field already holds for other providers'
        instance identifiers."""
        config = self._config()
        client = oci.monitoring.MonitoringClient(config)
        compartment_id = self._compartment_id()

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=lookback_minutes)

        def _query(metric_query: str) -> float | None:
            details = oci.monitoring.models.SummarizeMetricsDataDetails(
                namespace=_NAMESPACE,
                query=metric_query,
                start_time=start_time,
                end_time=end_time,
            )

            @_oci_retry
            def _summarize():
                return client.summarize_metrics_data(compartment_id, details)

            try:
                response = _summarize()
            except ServiceError as exc:
                raise ValidationAppError(
                    f"OCI Monitoring rejected the request ({exc.code}): {exc.message}",
                    code="OCI_MONITORING_REQUEST_FAILED",
                ) from exc

            for metric_data in response.data:
                points = metric_data.aggregated_datapoints or []
                if points:
                    return points[-1].value
            return None

        cpu = _query(f'CpuUtilization[1m]{{resourceId = "{resource_id}"}}.mean()')
        network_in = _query(f'NetworksBytesIn[1m]{{resourceId = "{resource_id}"}}.mean()')
        network_out = _query(f'NetworksBytesOut[1m]{{resourceId = "{resource_id}"}}.mean()')

        if cpu is None and network_in is None and network_out is None:
            raise ValidationAppError(
                f"OCI Monitoring returned no datapoints for instance '{resource_id}' "
                f"in the last {lookback_minutes} minutes",
                code="NO_OCI_MONITORING_DATA",
            )

        return {
            "cpu_usage_percent": cpu or 0.0,
            "memory_usage_mb": 0.0,
            "disk_usage_mb": 0.0,
            "network_in_kbps": (network_in or 0.0) * 8 / 1000,
            "network_out_kbps": (network_out or 0.0) * 8 / 1000,
            "recorded_at": end_time,
        }

    def _config_for(self, region: str) -> dict:
        self.authenticate()
        return {
            "user": self.credentials["user"],
            "tenancy": self.credentials["tenancy"],
            "fingerprint": self.credentials["fingerprint"],
            "key_content": self.credentials["key_content"],
            "region": region,
        }

    def list_resources(self, region: str) -> list[CloudResourceSummary]:
        config = self._config_for(region)
        client = oci.core.ComputeClient(config)

        @_oci_retry
        def _list_instances():
            return client.list_instances(self._compartment_id())

        try:
            response = _list_instances()
        except ServiceError as exc:
            raise ValidationAppError(
                f"OCI rejected the resource-inventory request ({exc.code}): {exc.message}",
                code="OCI_RESOURCE_INVENTORY_FAILED",
            ) from exc

        return [
            {
                "id": instance.id,
                "name": instance.display_name,
                "type": instance.shape,
                "region": region,
                "status": instance.lifecycle_state,
                "created_at": instance.time_created,
            }
            for instance in response.data
        ]

    def list_clusters(self, region: str) -> list[CloudResourceSummary]:
        config = self._config_for(region)
        client = oci.container_engine.ContainerEngineClient(config)

        @_oci_retry
        def _list_clusters():
            return client.list_clusters(self._compartment_id())

        try:
            response = _list_clusters()
        except ServiceError as exc:
            raise ValidationAppError(
                f"OCI rejected the cluster-inventory request ({exc.code}): {exc.message}",
                code="OCI_CLUSTER_INVENTORY_FAILED",
            ) from exc

        return [
            {
                "id": cluster.id,
                "name": cluster.name,
                "type": "oke",
                "region": region,
                "status": cluster.lifecycle_state,
                "created_at": getattr(cluster.metadata, "time_created", None) if cluster.metadata else None,
            }
            for cluster in response.data
        ]

    def list_databases(self, region: str) -> list[CloudResourceSummary]:
        config = self._config_for(region)
        client = oci.database.DatabaseClient(config)

        @_oci_retry
        def _list_db_systems():
            return client.list_db_systems(self._compartment_id())

        try:
            response = _list_db_systems()
        except ServiceError as exc:
            raise ValidationAppError(
                f"OCI rejected the database-inventory request ({exc.code}): {exc.message}",
                code="OCI_DATABASE_INVENTORY_FAILED",
            ) from exc

        return [
            {
                "id": db_system.id,
                "name": db_system.display_name,
                "type": db_system.database_edition or "db_system",
                "region": region,
                "status": db_system.lifecycle_state,
                "created_at": db_system.time_created,
            }
            for db_system in response.data
        ]

    def list_storage(self, region: str) -> list[CloudResourceSummary]:
        config = self._config_for(region)
        client = oci.object_storage.ObjectStorageClient(config)

        @_oci_retry
        def _list_buckets():
            namespace = client.get_namespace().data
            return client.list_buckets(namespace, self._compartment_id())

        try:
            response = _list_buckets()
        except ServiceError as exc:
            raise ValidationAppError(
                f"OCI rejected the storage-inventory request ({exc.code}): {exc.message}",
                code="OCI_STORAGE_INVENTORY_FAILED",
            ) from exc

        return [
            {
                "id": bucket.name,
                "name": bucket.name,
                "type": "object_storage_bucket",
                "region": region,
                "status": "available",
                "created_at": bucket.time_created,
            }
            for bucket in response.data
        ]

    def list_networking(self, region: str) -> list[CloudResourceSummary]:
        config = self._config_for(region)
        client = oci.core.VirtualNetworkClient(config)

        @_oci_retry
        def _list_vcns():
            return client.list_vcns(self._compartment_id())

        try:
            response = _list_vcns()
        except ServiceError as exc:
            raise ValidationAppError(
                f"OCI rejected the networking-inventory request ({exc.code}): {exc.message}",
                code="OCI_NETWORKING_INVENTORY_FAILED",
            ) from exc

        return [
            {
                "id": vcn.id,
                "name": vcn.display_name,
                "type": "vcn",
                "region": region,
                "status": vcn.lifecycle_state,
                "created_at": vcn.time_created,
            }
            for vcn in response.data
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
            return self._destroy_compute(region, resource_id)
        if resource_type == "storage":
            return self._destroy_storage(region, resource_id)
        if resource_type == "networking":
            return self._destroy_networking(region, resource_id)
        raise self._not_yet_supported(f"Provisioning of '{resource_type}'")

    @staticmethod
    def _require_spec(spec: dict, keys: tuple[str, ...]) -> None:
        missing = [k for k in keys if not spec.get(k)]
        if missing:
            raise ValidationAppError(
                f"OCI deploy requires spec.{', spec.'.join(missing)}", code="OCI_DEPLOY_SPEC_INCOMPLETE"
            )

    def _deploy_compute(self, region: str, spec: dict) -> CloudResourceSummary:
        # A real OCI compute instance needs an availability domain and a
        # subnet within the target VCN - both real, standard OCI
        # prerequisites this platform cannot fabricate on the caller's
        # behalf (the same honest stance as requiring an AMI id for AWS).
        self._require_spec(spec, ("image_id", "availability_domain", "subnet_id"))
        config = self._config_for(region)
        client = oci.core.ComputeClient(config)
        name = spec.get("name", "cloud-ai-platform-instance")
        details = oci.core.models.LaunchInstanceDetails(
            compartment_id=self._compartment_id(),
            availability_domain=spec["availability_domain"],
            shape=_DEPLOY_SHAPE,
            display_name=name,
            source_details=oci.core.models.InstanceSourceViaImageDetails(image_id=spec["image_id"]),
            create_vnic_details=oci.core.models.CreateVnicDetails(subnet_id=spec["subnet_id"]),
        )
        try:
            response = client.launch_instance(details)
        except ServiceError as exc:
            raise ValidationAppError(
                f"OCI rejected the deploy request ({exc.code}): {exc.message}", code="OCI_DEPLOY_FAILED"
            ) from exc

        instance = response.data
        return {
            "id": instance.id,
            "name": instance.display_name,
            "type": _DEPLOY_SHAPE,
            "region": region,
            "status": instance.lifecycle_state,
            "created_at": instance.time_created,
        }

    def _destroy_compute(self, region: str, resource_id: str) -> None:
        config = self._config_for(region)
        client = oci.core.ComputeClient(config)
        try:
            client.terminate_instance(resource_id)
        except ServiceError as exc:
            raise ValidationAppError(
                f"OCI rejected the destroy request ({exc.code}): {exc.message}", code="OCI_DESTROY_FAILED"
            ) from exc

    def _deploy_storage(self, region: str, spec: dict) -> CloudResourceSummary:
        name = spec.get("name")
        if not name:
            raise ValidationAppError(
                "OCI storage deploy requires spec.name (a bucket name, unique per namespace)",
                code="OCI_DEPLOY_SPEC_INCOMPLETE",
            )
        config = self._config_for(region)
        client = oci.object_storage.ObjectStorageClient(config)
        try:
            namespace = client.get_namespace().data
            details = oci.object_storage.models.CreateBucketDetails(
                name=name, compartment_id=self._compartment_id()
            )
            response = client.create_bucket(namespace, details)
        except ServiceError as exc:
            raise ValidationAppError(
                f"OCI rejected the deploy request ({exc.code}): {exc.message}", code="OCI_DEPLOY_FAILED"
            ) from exc

        bucket = response.data
        return {
            "id": bucket.name,
            "name": bucket.name,
            "type": "object_storage_bucket",
            "region": region,
            "status": "available",
            "created_at": bucket.time_created,
        }

    def _destroy_storage(self, region: str, resource_id: str) -> None:
        config = self._config_for(region)
        client = oci.object_storage.ObjectStorageClient(config)
        try:
            namespace = client.get_namespace().data
            # Requires an already-empty bucket - a real OCI precondition
            # this platform does not attempt to bypass by force-emptying it.
            client.delete_bucket(namespace, resource_id)
        except ServiceError as exc:
            raise ValidationAppError(
                f"OCI rejected the destroy request ({exc.code}): {exc.message}", code="OCI_DESTROY_FAILED"
            ) from exc

    def _deploy_networking(self, region: str, spec: dict) -> CloudResourceSummary:
        cidr_block = spec.get("cidr_block", "10.0.0.0/16")
        name = spec.get("name", "cloud-ai-platform-vcn")
        config = self._config_for(region)
        client = oci.core.VirtualNetworkClient(config)
        try:
            details = oci.core.models.CreateVcnDetails(
                cidr_block=cidr_block, compartment_id=self._compartment_id(), display_name=name
            )
            response = client.create_vcn(details)
        except ServiceError as exc:
            raise ValidationAppError(
                f"OCI rejected the deploy request ({exc.code}): {exc.message}", code="OCI_DEPLOY_FAILED"
            ) from exc

        vcn = response.data
        return {
            "id": vcn.id,
            "name": vcn.display_name,
            "type": "vcn",
            "region": region,
            "status": vcn.lifecycle_state,
            "created_at": vcn.time_created,
        }

    def _destroy_networking(self, region: str, resource_id: str) -> None:
        config = self._config_for(region)
        client = oci.core.VirtualNetworkClient(config)
        try:
            client.delete_vcn(resource_id)
        except ServiceError as exc:
            raise ValidationAppError(
                f"OCI rejected the destroy request ({exc.code}): {exc.message}", code="OCI_DESTROY_FAILED"
            ) from exc
