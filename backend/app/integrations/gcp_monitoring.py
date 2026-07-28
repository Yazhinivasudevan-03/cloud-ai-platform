"""Real Google Cloud Monitoring integration: fetches genuine Compute Engine
instance metrics using the `google-cloud-monitoring` SDK, for deployments
linked to a GCP CloudProviderAccount (see app/services/cloud_sync_service.py).
Mirrors app/integrations/aws_cloudwatch.py's shape and honesty exactly.

Only CPU utilization and network in/out are available from Compute Engine's
default metrics - memory and disk usage require the Ops Agent installed on
the instance itself, which this platform has no way to assume is present,
so those two ResourceUsage fields are reported as 0.0 here, with that
limitation disclosed rather than fabricated (same approach as
aws_cloudwatch.py/azure_monitor.py).

Real GCP *cost* data (unlike AWS Cost Explorer / Azure Cost Management) has
no equivalent "give me my spend by service" API a backend can call with
just account credentials - it requires the customer to have already set up
BigQuery billing export to a dataset only they control. That is
deliberately not built here (see app/services/cloud_cost_service.py's
_PROVIDER_COST_FETCHERS, which still reports GCP as not-yet-supported for
cost sync specifically) rather than faking a fragile integration.
"""
import json
from datetime import datetime, timedelta, timezone
from typing import TypedDict

import tenacity
from google.api_core.exceptions import (
    DeadlineExceeded,
    GoogleAPICallError,
    PermissionDenied,
    ServiceUnavailable,
    Unauthenticated,
)
from google.cloud import monitoring_v3
from google.oauth2 import service_account

from app.utils.exceptions import ValidationAppError

_CPU_METRIC = "compute.googleapis.com/instance/cpu/utilization"
_NETWORK_IN_METRIC = "compute.googleapis.com/instance/network/received_bytes_count"
_NETWORK_OUT_METRIC = "compute.googleapis.com/instance/network/sent_bytes_count"


def _is_retryable_gcp_error(exc: BaseException) -> bool:
    return isinstance(exc, (ServiceUnavailable, DeadlineExceeded))


_gcp_monitoring_retry = tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable_gcp_error),
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)


class InstanceResourceUsage(TypedDict):
    cpu_usage_percent: float
    memory_usage_mb: float
    disk_usage_mb: float
    network_in_kbps: float
    network_out_kbps: float
    recorded_at: datetime


def _query_latest_point(
    client: monitoring_v3.MetricServiceClient,
    project_name: str,
    metric_type: str,
    instance_id: str,
    interval: monitoring_v3.TimeInterval,
    aligner,
    alignment_period_seconds: int,
) -> tuple[float, datetime] | None:
    aggregation = monitoring_v3.Aggregation(
        {
            "alignment_period": {"seconds": alignment_period_seconds},
            "per_series_aligner": aligner,
        }
    )

    @_gcp_monitoring_retry
    def _list_time_series():
        return list(
            client.list_time_series(
                request={
                    "name": project_name,
                    "filter": (
                        f'metric.type = "{metric_type}" AND '
                        f'resource.labels.instance_id = "{instance_id}"'
                    ),
                    "interval": interval,
                    "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                    "aggregation": aggregation,
                }
            )
        )

    series_list = _list_time_series()

    latest_value: float | None = None
    latest_timestamp: datetime | None = None
    for series in series_list:
        for point in series.points:
            timestamp = point.interval.end_time
            if latest_timestamp is None or timestamp > latest_timestamp:
                latest_timestamp = timestamp
                latest_value = point.value.double_value or point.value.int64_value

    if latest_value is None or latest_timestamp is None:
        return None
    return latest_value, latest_timestamp


def fetch_instance_resource_usage(
    credentials: dict[str, str], region: str, resource_id: str, lookback_minutes: int
) -> InstanceResourceUsage:
    """Query real Cloud Monitoring metric data for a single Compute Engine
    instance over the last `lookback_minutes`, returning the most recent
    datapoint available for each metric, shaped to match
    ResourceUsageCreate directly so the caller (CloudSyncService) can hand
    the result straight to the existing resource-usage ingestion path.

    `resource_id` is the GCE instance's numeric instance ID (the value
    Cloud Monitoring's `resource.labels.instance_id` filter expects) - the
    same value the deployment's `cloud_resource_identifier` field already
    holds for AWS instance IDs / Azure resource URIs. `region` is accepted
    for call-signature compatibility with the other providers (see
    CloudSyncService._PROVIDER_FETCHERS) but unused - Cloud Monitoring
    queries are scoped by project and instance ID, not region.

    Raises ValidationAppError if credentials are missing required keys, or
    if Cloud Monitoring returns no datapoints for the window.
    """
    service_account_json = credentials.get("service_account_json")
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

    project_id = credentials.get("project_id") or service_account_info.get("project_id")
    if not project_id:
        raise ValidationAppError(
            "GCP credentials must include 'project_id' (or a service_account_json "
            "that itself contains one)",
            code="GCP_CREDENTIALS_INCOMPLETE",
        )

    google_credentials = service_account.Credentials.from_service_account_info(service_account_info)
    client = monitoring_v3.MetricServiceClient(credentials=google_credentials)
    project_name = f"projects/{project_id}"

    end_time = datetime.now(timezone.utc) + timedelta(minutes=1)
    start_time = end_time - timedelta(minutes=lookback_minutes + 1)
    interval = monitoring_v3.TimeInterval(
        {
            "end_time": {"seconds": int(end_time.timestamp())},
            "start_time": {"seconds": int(start_time.timestamp())},
        }
    )
    alignment_period_seconds = 60

    try:
        cpu_point = _query_latest_point(
            client, project_name, _CPU_METRIC, resource_id, interval,
            monitoring_v3.Aggregation.Aligner.ALIGN_MEAN, alignment_period_seconds,
        )
        network_in_point = _query_latest_point(
            client, project_name, _NETWORK_IN_METRIC, resource_id, interval,
            monitoring_v3.Aggregation.Aligner.ALIGN_RATE, alignment_period_seconds,
        )
        network_out_point = _query_latest_point(
            client, project_name, _NETWORK_OUT_METRIC, resource_id, interval,
            monitoring_v3.Aggregation.Aligner.ALIGN_RATE, alignment_period_seconds,
        )
    except (PermissionDenied, Unauthenticated) as exc:
        raise ValidationAppError(
            f"Cloud Monitoring rejected the credentials: {exc}",
            code="GCP_MONITORING_REQUEST_FAILED",
        ) from exc
    except GoogleAPICallError as exc:
        raise ValidationAppError(
            f"Cloud Monitoring rejected the request: {exc}", code="GCP_MONITORING_REQUEST_FAILED"
        ) from exc

    if cpu_point is None and network_in_point is None and network_out_point is None:
        raise ValidationAppError(
            f"Cloud Monitoring returned no datapoints for instance '{resource_id}' "
            f"in the last {lookback_minutes} minutes",
            code="NO_GCP_MONITORING_DATA",
        )

    # CPU utilization is reported as a 0-1 fraction; network in/out are
    # already bytes/sec after ALIGN_RATE - same bytes/sec -> kbps
    # conversion as aws_cloudwatch.py/azure_monitor.py.
    cpu_fraction, cpu_timestamp = cpu_point or (0.0, end_time)
    network_in_bytes_per_sec, network_in_timestamp = network_in_point or (0.0, end_time)
    network_out_bytes_per_sec, network_out_timestamp = network_out_point or (0.0, end_time)
    latest_timestamp = max(cpu_timestamp, network_in_timestamp, network_out_timestamp)

    return {
        "cpu_usage_percent": cpu_fraction * 100,
        "memory_usage_mb": 0.0,
        "disk_usage_mb": 0.0,
        "network_in_kbps": network_in_bytes_per_sec * 8 / 1000,
        "network_out_kbps": network_out_bytes_per_sec * 8 / 1000,
        "recorded_at": latest_timestamp,
    }
