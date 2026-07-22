"""Unit tests for the real AWS CloudWatch integration - verified against
moto's faithful CloudWatch API emulation (genuine boto3 calls, genuine
request/response serialization over HTTP, intercepted by moto rather than
reaching real AWS - no live AWS account needed, but the actual SDK code
path under test is exactly what would run against one)."""
from unittest.mock import patch

import pytest
from datetime import datetime, timezone

import boto3
import botocore.exceptions
from moto import mock_aws

from app.integrations.aws_cloudwatch import fetch_ec2_resource_usage
from app.utils.exceptions import ValidationAppError

FAKE_CREDENTIALS = {"access_key_id": "testing", "secret_access_key": "testing"}


def _seed_datapoint(instance_id: str, cpu: float, network_in: float, network_out: float) -> None:
    client = boto3.client(
        "cloudwatch",
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    now = datetime.now(timezone.utc)
    client.put_metric_data(
        Namespace="AWS/EC2",
        MetricData=[
            {
                "MetricName": "CPUUtilization",
                "Dimensions": [{"Name": "InstanceId", "Value": instance_id}],
                "Timestamp": now,
                "Value": cpu,
                "Unit": "Percent",
            },
            {
                "MetricName": "NetworkIn",
                "Dimensions": [{"Name": "InstanceId", "Value": instance_id}],
                "Timestamp": now,
                "Value": network_in,
                "Unit": "Bytes",
            },
            {
                "MetricName": "NetworkOut",
                "Dimensions": [{"Name": "InstanceId", "Value": instance_id}],
                "Timestamp": now,
                "Value": network_out,
                "Unit": "Bytes",
            },
        ],
    )


@mock_aws
def test_fetch_ec2_resource_usage_parses_real_cloudwatch_response():
    _seed_datapoint("i-fake123", cpu=42.5, network_in=1_000_000.0, network_out=500_000.0)

    result = fetch_ec2_resource_usage(FAKE_CREDENTIALS, "us-east-1", "i-fake123", lookback_minutes=15)

    assert result["cpu_usage_percent"] == pytest.approx(42.5)
    assert result["network_in_kbps"] > 0
    assert result["network_out_kbps"] > 0
    assert result["network_out_kbps"] != result["network_in_kbps"]  # sanity-check the two aren't accidentally swapped
    assert result["memory_usage_mb"] == 0.0
    assert result["disk_usage_mb"] == 0.0
    assert isinstance(result["recorded_at"], datetime)


@mock_aws
def test_fetch_ec2_resource_usage_network_conversion_is_correct():
    # Fixed 60s query period (see aws_cloudwatch.py): 6000 bytes/60s = 100
    # bytes/sec = 0.1 KB/sec = 0.8 kbps... expressed the way the code does
    # it: (6000 / 60) * 8 / 1000 = 0.8 kbps.
    _seed_datapoint("i-conversion-test", cpu=10.0, network_in=6000.0, network_out=0.0)

    result = fetch_ec2_resource_usage(
        FAKE_CREDENTIALS, "us-east-1", "i-conversion-test", lookback_minutes=15
    )

    assert result["network_in_kbps"] == pytest.approx(0.8, rel=0.01)


@mock_aws
def test_fetch_ec2_resource_usage_raises_when_no_datapoints():
    with pytest.raises(ValidationAppError) as exc_info:
        fetch_ec2_resource_usage(FAKE_CREDENTIALS, "us-east-1", "i-does-not-exist", lookback_minutes=15)
    assert exc_info.value.code == "NO_CLOUDWATCH_DATA"


def test_fetch_ec2_resource_usage_requires_access_key_and_secret():
    with pytest.raises(ValidationAppError) as exc_info:
        fetch_ec2_resource_usage({}, "us-east-1", "i-fake123", lookback_minutes=15)
    assert exc_info.value.code == "AWS_CREDENTIALS_INCOMPLETE"


@mock_aws
def test_fetch_ec2_resource_usage_wraps_invalid_credentials_cleanly():
    # moto itself doesn't validate credentials (any access key "works"), so
    # this simulates the real-AWS failure mode - InvalidClientTokenId -
    # directly, verifying it surfaces as a clean ValidationAppError rather
    # than an unhandled 500 (found via live manual verification against a
    # real, deliberately-fake credential pair).
    error_response = {"Error": {"Code": "InvalidClientTokenId", "Message": "The security token is invalid"}}
    client_error = botocore.exceptions.ClientError(error_response, "GetMetricData")

    with patch("boto3.client") as mock_client_factory:
        mock_client_factory.return_value.get_metric_data.side_effect = client_error
        with pytest.raises(ValidationAppError) as exc_info:
            fetch_ec2_resource_usage(FAKE_CREDENTIALS, "us-east-1", "i-fake123", lookback_minutes=15)

    assert exc_info.value.code == "CLOUDWATCH_REQUEST_FAILED"
    assert "InvalidClientTokenId" in str(exc_info.value)


# --- Retry/backoff on transient failures ------------------------------------


def _fake_metric_data_response() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "MetricDataResults": [
            {"Id": "cpuutilization", "Values": [55.0], "Timestamps": [now]},
            {"Id": "networkin", "Values": [], "Timestamps": []},
            {"Id": "networkout", "Values": [], "Timestamps": []},
        ]
    }


def test_fetch_ec2_resource_usage_retries_transient_error_then_succeeds():
    # Throttling is a genuinely transient AWS response - the retry should
    # transparently succeed on the second attempt rather than surfacing an
    # error to the caller.
    error_response = {"Error": {"Code": "Throttling", "Message": "Rate exceeded"}}
    throttling_error = botocore.exceptions.ClientError(error_response, "GetMetricData")

    with patch("boto3.client") as mock_client_factory:
        mock_client_factory.return_value.get_metric_data.side_effect = [
            throttling_error,
            _fake_metric_data_response(),
        ]
        result = fetch_ec2_resource_usage(FAKE_CREDENTIALS, "us-east-1", "i-fake123", lookback_minutes=15)

    assert result["cpu_usage_percent"] == pytest.approx(55.0)
    assert mock_client_factory.return_value.get_metric_data.call_count == 2


def test_fetch_ec2_resource_usage_does_not_retry_non_transient_client_error():
    # InvalidClientTokenId (bad credentials) is a config error, not a
    # transient one - retrying it 3 times would only waste time before
    # failing anyway, so it must fail on the very first attempt.
    error_response = {"Error": {"Code": "InvalidClientTokenId", "Message": "The security token is invalid"}}
    client_error = botocore.exceptions.ClientError(error_response, "GetMetricData")

    with patch("boto3.client") as mock_client_factory:
        mock_client_factory.return_value.get_metric_data.side_effect = client_error
        with pytest.raises(ValidationAppError):
            fetch_ec2_resource_usage(FAKE_CREDENTIALS, "us-east-1", "i-fake123", lookback_minutes=15)

    assert mock_client_factory.return_value.get_metric_data.call_count == 1
