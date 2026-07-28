"""Real Azure Monitor integration: fetches genuine VM metrics using the
`azure-monitor-query` SDK (Microsoft's current recommended package for
querying metrics - simpler than the older `azure-mgmt-monitor`), for
deployments linked to an Azure CloudProviderAccount (see
app/services/cloud_sync_service.py). Mirrors app/integrations/aws_cloudwatch.py's
shape and honesty exactly.

Only "Percentage CPU" and network in/out are available without extra setup
- memory and disk usage require the Azure Monitor Agent installed on the VM
itself, which this platform has no way to assume is present, so those two
ResourceUsage fields are reported as 0.0 here, with that limitation
disclosed rather than fabricated (same approach as aws_cloudwatch.py).
"""
from datetime import datetime, timedelta, timezone
from typing import TypedDict

import tenacity
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError, ServiceRequestError
from azure.identity import ClientSecretCredential
from azure.monitor.query import MetricAggregationType, MetricsQueryClient

from app.utils.exceptions import ValidationAppError

_METRIC_NAMES = ["Percentage CPU", "Network In Total", "Network Out Total"]

# Retries only genuinely transient failures - matching the same policy as
# app/integrations/aws_cloudwatch.py.
_RETRYABLE_STATUS_CODES = {429, 500, 503}


def _is_retryable_azure_error(exc: BaseException) -> bool:
    if isinstance(exc, HttpResponseError):
        return exc.status_code in _RETRYABLE_STATUS_CODES
    return isinstance(exc, ServiceRequestError)


_azure_monitor_retry = tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable_azure_error),
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)


class VmResourceUsage(TypedDict):
    cpu_usage_percent: float
    memory_usage_mb: float
    disk_usage_mb: float
    network_in_kbps: float
    network_out_kbps: float
    recorded_at: datetime


def fetch_vm_resource_usage(
    credentials: dict[str, str], region: str, resource_id: str, lookback_minutes: int
) -> VmResourceUsage:
    """Query real Azure Monitor metric data for a single VM resource over
    the last `lookback_minutes`, returning the most recent datapoint
    available for each metric, shaped to match ResourceUsageCreate
    directly so the caller (CloudSyncService) can hand the result straight
    to the existing resource-usage ingestion path.

    `resource_id` is the VM's full Azure resource URI (e.g.
    "/subscriptions/.../resourceGroups/.../providers/Microsoft.Compute/
    virtualMachines/my-vm") - the same value the deployment's
    `cloud_resource_identifier` field already holds for AWS instance IDs.
    `region` is accepted for call-signature compatibility with the other
    providers (see CloudSyncService._PROVIDER_FETCHERS) but unused - Azure
    Monitor queries operate on the resource URI directly and are already
    region-scoped by the resource itself.

    Raises ValidationAppError if credentials are missing required keys, or
    if Azure Monitor returns no datapoints for the window.
    """
    tenant_id = credentials.get("tenant_id")
    client_id = credentials.get("client_id")
    client_secret = credentials.get("client_secret")
    if not tenant_id or not client_id or not client_secret:
        raise ValidationAppError(
            "Azure credentials must include 'tenant_id', 'client_id' and 'client_secret'",
            code="AZURE_CREDENTIALS_INCOMPLETE",
        )

    credential = ClientSecretCredential(tenant_id, client_id, client_secret)
    client = MetricsQueryClient(credential)

    end_time = datetime.now(timezone.utc) + timedelta(minutes=1)
    start_time = end_time - timedelta(minutes=lookback_minutes + 1)
    granularity = timedelta(minutes=1)

    @_azure_monitor_retry
    def _query_metrics():
        return client.query_resource(
            resource_id,
            metric_names=_METRIC_NAMES,
            timespan=(start_time, end_time),
            granularity=granularity,
            aggregations=[MetricAggregationType.AVERAGE],
        )

    try:
        response = _query_metrics()
    except ClientAuthenticationError as exc:
        raise ValidationAppError(
            f"Azure Monitor rejected the credentials: {exc}", code="AZURE_MONITOR_REQUEST_FAILED"
        ) from exc
    except HttpResponseError as exc:
        raise ValidationAppError(
            f"Azure Monitor rejected the request: {exc.message or exc}",
            code="AZURE_MONITOR_REQUEST_FAILED",
        ) from exc
    except ServiceRequestError as exc:
        raise ValidationAppError(
            f"Could not reach Azure Monitor: {exc}", code="AZURE_MONITOR_REQUEST_FAILED"
        ) from exc

    values: dict[str, float] = {}
    latest_timestamp: datetime | None = None
    for metric in response.metrics:
        for timeseries in metric.timeseries:
            for data_point in timeseries.data:
                if data_point.average is None:
                    continue
                values[metric.name] = data_point.average
                if latest_timestamp is None or data_point.timestamp > latest_timestamp:
                    latest_timestamp = data_point.timestamp

    if not values:
        raise ValidationAppError(
            f"Azure Monitor returned no datapoints for resource '{resource_id}' "
            f"in the last {lookback_minutes} minutes",
            code="NO_AZURE_MONITOR_DATA",
        )

    # Network In/Out Total are reported by Azure Monitor as total bytes over
    # the requested granularity - same bytes-over-period -> kbps conversion
    # as aws_cloudwatch.py, using the 60s granularity above as the period.
    period_seconds = granularity.total_seconds()
    network_in_bytes_per_period = values.get("Network In Total", 0.0)
    network_out_bytes_per_period = values.get("Network Out Total", 0.0)

    return {
        "cpu_usage_percent": values.get("Percentage CPU", 0.0),
        "memory_usage_mb": 0.0,
        "disk_usage_mb": 0.0,
        "network_in_kbps": (network_in_bytes_per_period / period_seconds) * 8 / 1000,
        "network_out_kbps": (network_out_bytes_per_period / period_seconds) * 8 / 1000,
        "recorded_at": latest_timestamp or end_time,
    }
