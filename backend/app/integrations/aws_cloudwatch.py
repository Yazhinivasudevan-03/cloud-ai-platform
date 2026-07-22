"""Real AWS CloudWatch integration: fetches genuine EC2 instance metrics
using boto3, for deployments linked to an AWS CloudProviderAccount (see
app/services/cloud_sync_service.py).

Only CPU and network are available from EC2's default ("basic") CloudWatch
monitoring - memory and disk usage require the CloudWatch Agent installed
on the instance itself, which this platform has no way to assume is
present, so those two ResourceUsage fields are reported as 0.0 here, with
that limitation disclosed rather than fabricated (see docs/PHASE_12.md).
"""
from datetime import datetime, timedelta, timezone
from typing import TypedDict

import boto3
import botocore.exceptions
import tenacity

from app.utils.exceptions import ValidationAppError

_NAMESPACE = "AWS/EC2"
_METRICS = ["CPUUtilization", "NetworkIn", "NetworkOut"]

# Retries only genuinely transient failures - throttling and connection-level
# issues - a few times with short backoff, so a momentary AWS API blip
# doesn't fail an entire scheduled sync run. A non-transient rejection
# (bad credentials, unknown instance) is a config problem no amount of
# retrying fixes, so those fail on the first attempt as before.
_RETRYABLE_CLIENT_ERROR_CODES = {
    "Throttling",
    "ThrottlingException",
    "RequestLimitExceeded",
    "TooManyRequestsException",
    "ServiceUnavailable",
    "InternalError",
    "RequestTimeout",
}


def _is_retryable_aws_error(exc: BaseException) -> bool:
    if isinstance(exc, botocore.exceptions.ClientError):
        return exc.response.get("Error", {}).get("Code") in _RETRYABLE_CLIENT_ERROR_CODES
    return isinstance(exc, botocore.exceptions.BotoCoreError)


_cloudwatch_retry = tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable_aws_error),
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)


class Ec2ResourceUsage(TypedDict):
    cpu_usage_percent: float
    memory_usage_mb: float
    disk_usage_mb: float
    network_in_kbps: float
    network_out_kbps: float
    recorded_at: datetime


def fetch_ec2_resource_usage(
    credentials: dict[str, str], region: str, instance_id: str, lookback_minutes: int
) -> Ec2ResourceUsage:
    """Query real CloudWatch metric data for a single EC2 instance over the
    last `lookback_minutes`, returning the most recent datapoint available
    for each metric, shaped to match ResourceUsageCreate directly so the
    caller (CloudSyncService) can hand the result straight to the existing
    resource-usage ingestion path.

    Raises ValidationAppError if credentials are missing required keys, or
    if CloudWatch returns no datapoints for the window (e.g. the instance
    isn't running, or the credentials/instance ID don't correspond to
    anything reachable).
    """
    access_key_id = credentials.get("access_key_id")
    secret_access_key = credentials.get("secret_access_key")
    if not access_key_id or not secret_access_key:
        raise ValidationAppError(
            "AWS credentials must include 'access_key_id' and 'secret_access_key'",
            code="AWS_CREDENTIALS_INCOMPLETE",
        )

    client_kwargs: dict[str, str] = {
        "region_name": region,
        "aws_access_key_id": access_key_id,
        "aws_secret_access_key": secret_access_key,
    }
    session_token = credentials.get("session_token")
    if session_token:
        client_kwargs["aws_session_token"] = session_token
    # Only ever set for testing against a real API-compatible emulator
    # (e.g. LocalStack) - a genuine AWS account never needs this.
    endpoint_url = credentials.get("endpoint_url")
    if endpoint_url:
        client_kwargs["endpoint_url"] = endpoint_url

    client = boto3.client("cloudwatch", **client_kwargs)

    # CloudWatch's Period buckets are [T, T+period) - a query whose EndTime
    # lands exactly on "now" can exclude a datapoint stamped at "now" because
    # its bucket hasn't closed yet as far as the query window is concerned.
    # A short forward buffer avoids racing the clock for what should be the
    # most recent minute's reading.
    end_time = datetime.now(timezone.utc) + timedelta(minutes=1)
    start_time = end_time - timedelta(minutes=lookback_minutes + 1)
    # Deliberately the finest CloudWatch-valid granularity (60s), not one
    # big bucket spanning the whole lookback window: for "real-time" data
    # this should return the single most recent minute's reading, not a
    # blurry average smeared across the entire window. lookback_minutes
    # only controls how far back to search if the most recent minute
    # hasn't reported yet.
    period_seconds = 60

    @_cloudwatch_retry
    def _get_metric_data():
        return client.get_metric_data(
            MetricDataQueries=[
                {
                    "Id": metric.lower(),
                    "MetricStat": {
                        "Metric": {
                            "Namespace": _NAMESPACE,
                            "MetricName": metric,
                            "Dimensions": [{"Name": "InstanceId", "Value": instance_id}],
                        },
                        "Period": period_seconds,
                        "Stat": "Average",
                    },
                }
                for metric in _METRICS
            ],
            StartTime=start_time,
            EndTime=end_time,
        )

    try:
        response = _get_metric_data()
    except botocore.exceptions.ClientError as exc:
        # Covers invalid/expired/revoked credentials, insufficient IAM
        # permissions, throttling, bad region, etc. - anything CloudWatch
        # itself rejected the request for, surfaced as a clean user-facing
        # error instead of an unhandled 500.
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        raise ValidationAppError(
            f"AWS CloudWatch rejected the request ({error_code}): {exc.response.get('Error', {}).get('Message', str(exc))}",
            code="CLOUDWATCH_REQUEST_FAILED",
        ) from exc
    except botocore.exceptions.BotoCoreError as exc:
        # Covers network/connection-level failures (no route to the AWS
        # endpoint, DNS failure, etc.) that never get as far as a structured
        # ClientError response.
        raise ValidationAppError(
            f"Could not reach AWS CloudWatch: {exc}", code="CLOUDWATCH_REQUEST_FAILED"
        ) from exc

    values: dict[str, float] = {}
    latest_timestamp: datetime | None = None
    for result in response["MetricDataResults"]:
        if result["Values"]:
            values[result["Id"]] = result["Values"][0]
            timestamp = result["Timestamps"][0]
            if latest_timestamp is None or timestamp > latest_timestamp:
                latest_timestamp = timestamp

    if not values:
        raise ValidationAppError(
            f"CloudWatch returned no datapoints for instance '{instance_id}' "
            f"in the last {lookback_minutes} minutes",
            code="NO_CLOUDWATCH_DATA",
        )

    # NetworkIn/NetworkOut are reported by CloudWatch as total bytes over
    # the requested period - dividing by the period length converts that
    # into bytes/sec, then *8/1000 converts to kilobits/sec (kbps) to match
    # ResourceUsage.network_in_kbps / network_out_kbps directly.
    network_in_bytes_per_period = values.get("networkin", 0.0)
    network_out_bytes_per_period = values.get("networkout", 0.0)

    return {
        "cpu_usage_percent": values.get("cpuutilization", 0.0),
        "memory_usage_mb": 0.0,
        "disk_usage_mb": 0.0,
        "network_in_kbps": (network_in_bytes_per_period / period_seconds) * 8 / 1000,
        "network_out_kbps": (network_out_bytes_per_period / period_seconds) * 8 / 1000,
        "recorded_at": latest_timestamp or end_time,
    }
