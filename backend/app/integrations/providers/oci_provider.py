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

from app.integrations.cloud_provider_client import CloudProviderClient, CloudRegionInfo
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
            raise ValidationAppError(
                f"OCI rejected the region-discovery request ({exc.code}): {exc.message}",
                code="OCI_REGION_DISCOVERY_FAILED",
            ) from exc

        return [
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
