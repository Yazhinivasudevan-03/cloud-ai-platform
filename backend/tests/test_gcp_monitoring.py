"""Unit tests for the real GCP Cloud Monitoring integration - patches the
`google-cloud-monitoring` SDK client directly (no GCP emulator available),
mirroring the patched-client half of test_aws_cloudwatch.py."""
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from google.api_core.exceptions import DeadlineExceeded, PermissionDenied, ServiceUnavailable

from app.integrations.gcp_monitoring import fetch_instance_resource_usage
from app.utils.exceptions import ValidationAppError

FAKE_SERVICE_ACCOUNT_INFO = {
    "type": "service_account",
    "project_id": "fake-project",
    "client_email": "fake@fake-project.iam.gserviceaccount.com",
}
FAKE_CREDENTIALS = {"service_account_json": json.dumps(FAKE_SERVICE_ACCOUNT_INFO)}
INSTANCE_ID = "1234567890123456789"


def _fake_time_series(value: float, timestamp: datetime) -> SimpleNamespace:
    point = SimpleNamespace(
        interval=SimpleNamespace(end_time=timestamp),
        value=SimpleNamespace(double_value=value, int64_value=0),
    )
    return SimpleNamespace(points=[point])


@patch("app.integrations.gcp_monitoring.service_account")
@patch("app.integrations.gcp_monitoring.monitoring_v3.MetricServiceClient")
def test_fetch_instance_resource_usage_parses_a_realistic_response(mock_client_cls, mock_service_account):
    now = datetime.now(timezone.utc)
    mock_client_cls.return_value.list_time_series.side_effect = [
        [_fake_time_series(0.425, now)],  # CPU: 0.425 fraction -> 42.5%
        [_fake_time_series(100.0, now)],  # network in: 100 bytes/sec (post ALIGN_RATE)
        [_fake_time_series(50.0, now)],  # network out: 50 bytes/sec
    ]

    result = fetch_instance_resource_usage(FAKE_CREDENTIALS, "us-central1", INSTANCE_ID, lookback_minutes=15)

    assert result["cpu_usage_percent"] == pytest.approx(42.5)
    assert result["network_in_kbps"] == pytest.approx(0.8, rel=0.01)
    assert result["network_out_kbps"] == pytest.approx(0.4, rel=0.01)
    assert result["memory_usage_mb"] == 0.0
    assert result["disk_usage_mb"] == 0.0
    assert result["recorded_at"] == now


def test_fetch_instance_resource_usage_requires_service_account_json():
    with pytest.raises(ValidationAppError) as exc_info:
        fetch_instance_resource_usage({}, "us-central1", INSTANCE_ID, lookback_minutes=15)
    assert exc_info.value.code == "GCP_CREDENTIALS_INCOMPLETE"


def test_fetch_instance_resource_usage_rejects_invalid_json():
    with pytest.raises(ValidationAppError) as exc_info:
        fetch_instance_resource_usage(
            {"service_account_json": "not-json"}, "us-central1", INSTANCE_ID, lookback_minutes=15
        )
    assert exc_info.value.code == "GCP_CREDENTIALS_INCOMPLETE"


@patch("app.integrations.gcp_monitoring.service_account")
@patch("app.integrations.gcp_monitoring.monitoring_v3.MetricServiceClient")
def test_fetch_instance_resource_usage_raises_when_no_datapoints(mock_client_cls, mock_service_account):
    mock_client_cls.return_value.list_time_series.return_value = []

    with pytest.raises(ValidationAppError) as exc_info:
        fetch_instance_resource_usage(FAKE_CREDENTIALS, "us-central1", INSTANCE_ID, lookback_minutes=15)
    assert exc_info.value.code == "NO_GCP_MONITORING_DATA"


@patch("app.integrations.gcp_monitoring.service_account")
@patch("app.integrations.gcp_monitoring.monitoring_v3.MetricServiceClient")
def test_fetch_instance_resource_usage_wraps_invalid_credentials_cleanly(mock_client_cls, mock_service_account):
    mock_client_cls.return_value.list_time_series.side_effect = PermissionDenied("bad credentials")

    with pytest.raises(ValidationAppError) as exc_info:
        fetch_instance_resource_usage(FAKE_CREDENTIALS, "us-central1", INSTANCE_ID, lookback_minutes=15)
    assert exc_info.value.code == "GCP_MONITORING_REQUEST_FAILED"


@patch("app.integrations.gcp_monitoring.service_account")
@patch("app.integrations.gcp_monitoring.monitoring_v3.MetricServiceClient")
def test_fetch_instance_resource_usage_retries_transient_error_then_succeeds(mock_client_cls, mock_service_account):
    now = datetime.now(timezone.utc)
    mock_client_cls.return_value.list_time_series.side_effect = [
        ServiceUnavailable("temporarily unavailable"),
        [_fake_time_series(0.1, now)],
        [_fake_time_series(0.0, now)],
        [_fake_time_series(0.0, now)],
    ]

    result = fetch_instance_resource_usage(FAKE_CREDENTIALS, "us-central1", INSTANCE_ID, lookback_minutes=15)

    assert result["cpu_usage_percent"] == pytest.approx(10.0)
    assert mock_client_cls.return_value.list_time_series.call_count == 4


@patch("app.integrations.gcp_monitoring.service_account")
@patch("app.integrations.gcp_monitoring.monitoring_v3.MetricServiceClient")
def test_fetch_instance_resource_usage_does_not_retry_permission_denied(mock_client_cls, mock_service_account):
    mock_client_cls.return_value.list_time_series.side_effect = PermissionDenied("forbidden")

    with pytest.raises(ValidationAppError):
        fetch_instance_resource_usage(FAKE_CREDENTIALS, "us-central1", INSTANCE_ID, lookback_minutes=15)

    assert mock_client_cls.return_value.list_time_series.call_count == 1
