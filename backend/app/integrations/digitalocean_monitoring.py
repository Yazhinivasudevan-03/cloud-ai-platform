"""Real DigitalOcean Droplet metrics integration (Phase 28): fetches genuine
CPU/memory/disk/network usage via `pydo`'s `monitoring` namespace, DigitalOcean's
own real, documented Prometheus-compatible metrics API (`/v2/monitoring/metrics/
droplet/*`). Mirrors app/integrations/aws_cloudwatch.py's shape and honesty.

Unlike every other provider in this platform, DigitalOcean's Droplet metrics
genuinely include memory and disk (not just CPU/network) without requiring a
separately-installed agent - the monitoring agent ships pre-installed on
every Droplet by default. This is disclosed here as a real capability, not
assumed - see docs/PHASE_28.md for the caveat that this was verified only
against mocked SDK responses (no live DigitalOcean account available), same
as every other provider integration in this project without moto-equivalent
emulation.

CPU is reported by DigitalOcean as a Prometheus-style counter broken down by
`mode` label (idle/user/system/iowait/...), not a single ready-made
percentage - `cpu_usage_percent` is derived as `100 - idle%` when an "idle"
series is present (the standard Linux CPU-accounting convention), falling
back to the sum of all non-idle series otherwise.
"""
from datetime import datetime, timedelta, timezone
from typing import Callable, TypedDict

import pydo
import tenacity
from azure.core.exceptions import HttpResponseError

from app.utils.exceptions import ValidationAppError

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _is_retryable_do_error(exc: BaseException) -> bool:
    return isinstance(exc, HttpResponseError) and exc.status_code in _RETRYABLE_STATUS_CODES


_do_monitoring_retry = tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable_do_error),
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)


class DropletResourceUsage(TypedDict):
    cpu_usage_percent: float
    memory_usage_mb: float
    disk_usage_mb: float
    network_in_kbps: float
    network_out_kbps: float
    recorded_at: datetime


def _latest_value(response: dict, series_filter: Callable[[dict], bool] | None = None) -> float | None:
    """Prometheus "matrix" response shape: {"data": {"result": [{"metric":
    {...}, "values": [[timestamp, "value_as_string"], ...]}]}} - takes the
    most recent datapoint from the first series matching `series_filter`
    (or the first series at all, when no filter is given)."""
    for series in response.get("data", {}).get("result", []):
        if series_filter is not None and not series_filter(series.get("metric", {})):
            continue
        values = series.get("values", [])
        if values:
            return float(values[-1][1])
    return None


def _cpu_usage_percent(response: dict) -> float | None:
    idle = _latest_value(response, lambda metric: metric.get("mode") == "idle")
    if idle is not None:
        return max(0.0, 100.0 - idle)

    total = 0.0
    found = False
    for series in response.get("data", {}).get("result", []):
        values = series.get("values", [])
        if values:
            total += float(values[-1][1])
            found = True
    return total if found else None


def fetch_droplet_resource_usage(
    credentials: dict[str, str], region: str, resource_id: str, lookback_minutes: int
) -> DropletResourceUsage:
    """Queries real DigitalOcean Droplet metrics for the last
    `lookback_minutes`, returning the most recent datapoint available for
    each metric, shaped to match ResourceUsageCreate directly so the
    caller (CloudSyncService) can hand the result straight to the existing
    resource-usage ingestion path.

    `resource_id` is the Droplet's numeric ID (as a string) - the same
    value list_resources()/deploy() already return as `id`. `region` is
    accepted for call-signature compatibility with the other providers
    (see CloudSyncService._PROVIDER_FETCHERS) but unused - DigitalOcean's
    monitoring API is scoped by Droplet ID, not region.

    Raises ValidationAppError if credentials are missing required keys, or
    if DigitalOcean returns no datapoints at all for the window (a Droplet
    with monitoring disabled, or too new to have reported yet).
    """
    api_token = credentials.get("api_token")
    if not api_token:
        raise ValidationAppError(
            "DigitalOcean credentials must include 'api_token' (a personal access token)",
            code="DIGITALOCEAN_CREDENTIALS_INCOMPLETE",
        )

    client = pydo.Client(token=api_token)
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=lookback_minutes)
    start_ts, end_ts = str(int(start.timestamp())), str(int(end.timestamp()))

    @_do_monitoring_retry
    def _metric(fn, **kwargs):
        return fn(host_id=resource_id, start=start_ts, end=end_ts, **kwargs)

    try:
        cpu_response = _metric(client.monitoring.get_droplet_cpu_metrics)
        memory_total_response = _metric(client.monitoring.get_droplet_memory_total_metrics)
        memory_available_response = _metric(client.monitoring.get_droplet_memory_available_metrics)
        disk_total_response = _metric(client.monitoring.get_droplet_filesystem_size_metrics)
        disk_free_response = _metric(client.monitoring.get_droplet_filesystem_free_metrics)
        network_in_response = _metric(client.monitoring.get_droplet_bandwidth_metrics, interface="public", direction="inbound")
        network_out_response = _metric(client.monitoring.get_droplet_bandwidth_metrics, interface="public", direction="outbound")
    except HttpResponseError as exc:
        raise ValidationAppError(
            f"DigitalOcean Monitoring rejected the request: {exc.message or exc}",
            code="DIGITALOCEAN_MONITORING_REQUEST_FAILED",
        ) from exc

    cpu_percent = _cpu_usage_percent(cpu_response)
    memory_total_bytes = _latest_value(memory_total_response)
    memory_available_bytes = _latest_value(memory_available_response)
    disk_total_bytes = _latest_value(disk_total_response)
    disk_free_bytes = _latest_value(disk_free_response)
    network_in_mbps = _latest_value(network_in_response)
    network_out_mbps = _latest_value(network_out_response)

    if (
        cpu_percent is None
        and memory_total_bytes is None
        and disk_total_bytes is None
        and network_in_mbps is None
        and network_out_mbps is None
    ):
        raise ValidationAppError(
            f"DigitalOcean Monitoring returned no datapoints for Droplet '{resource_id}' in the "
            f"last {lookback_minutes} minutes - monitoring may not yet be reporting for a very "
            "new Droplet",
            code="NO_DIGITALOCEAN_MONITORING_DATA",
        )

    memory_usage_mb = 0.0
    if memory_total_bytes is not None and memory_available_bytes is not None:
        memory_usage_mb = max(0.0, memory_total_bytes - memory_available_bytes) / (1024 * 1024)

    disk_usage_mb = 0.0
    if disk_total_bytes is not None and disk_free_bytes is not None:
        disk_usage_mb = max(0.0, disk_total_bytes - disk_free_bytes) / (1024 * 1024)

    return {
        "cpu_usage_percent": cpu_percent or 0.0,
        "memory_usage_mb": memory_usage_mb,
        "disk_usage_mb": disk_usage_mb,
        # Bandwidth metrics are published in Mbps - converting to kbps
        # matches every other provider's network_in_kbps/network_out_kbps.
        "network_in_kbps": (network_in_mbps or 0.0) * 1000,
        "network_out_kbps": (network_out_mbps or 0.0) * 1000,
        "recorded_at": end,
    }
