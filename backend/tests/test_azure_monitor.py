"""Unit tests for the real Azure Monitor integration.

Unlike AWS (moto has a faithful CloudWatch emulator), there is no
comparable Azure emulator available here, so these tests patch the
`azure-monitor-query` SDK client directly - the same dual approach
(patched-client unit tests) already used in test_aws_cloudwatch.py for
parsing/error-path coverage, just without the extra moto-backed
full-request test AWS also gets."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError, ServiceRequestError

from app.integrations.azure_monitor import fetch_vm_resource_usage
from app.utils.exceptions import ValidationAppError

FAKE_CREDENTIALS = {
    "tenant_id": "fake-tenant",
    "client_id": "fake-client",
    "client_secret": "fake-secret",
}
RESOURCE_ID = (
    "/subscriptions/fake-sub/resourceGroups/fake-rg/providers/"
    "Microsoft.Compute/virtualMachines/fake-vm"
)


def _fake_metric_value(value: float, timestamp: datetime) -> SimpleNamespace:
    return SimpleNamespace(average=value, timestamp=timestamp)


def _fake_response(cpu: float, network_in: float, network_out: float, timestamp: datetime):
    return SimpleNamespace(
        metrics=[
            SimpleNamespace(
                name="Percentage CPU",
                timeseries=[SimpleNamespace(data=[_fake_metric_value(cpu, timestamp)])],
            ),
            SimpleNamespace(
                name="Network In Total",
                timeseries=[SimpleNamespace(data=[_fake_metric_value(network_in, timestamp)])],
            ),
            SimpleNamespace(
                name="Network Out Total",
                timeseries=[SimpleNamespace(data=[_fake_metric_value(network_out, timestamp)])],
            ),
        ]
    )


def test_fetch_vm_resource_usage_parses_a_realistic_response():
    now = datetime.now(timezone.utc)
    with patch("app.integrations.azure_monitor.ClientSecretCredential"), patch(
        "app.integrations.azure_monitor.MetricsQueryClient"
    ) as mock_client_factory:
        mock_client_factory.return_value.query_resource.return_value = _fake_response(
            42.5, 6000.0, 3000.0, now
        )
        result = fetch_vm_resource_usage(FAKE_CREDENTIALS, "eastus", RESOURCE_ID, lookback_minutes=15)

    assert result["cpu_usage_percent"] == pytest.approx(42.5)
    # 60s granularity: 6000 bytes/60s = 100 bytes/sec = 0.8 kbps.
    assert result["network_in_kbps"] == pytest.approx(0.8, rel=0.01)
    assert result["network_out_kbps"] == pytest.approx(0.4, rel=0.01)
    assert result["memory_usage_mb"] == 0.0
    assert result["disk_usage_mb"] == 0.0
    assert result["recorded_at"] == now


def test_fetch_vm_resource_usage_requires_tenant_client_and_secret():
    with pytest.raises(ValidationAppError) as exc_info:
        fetch_vm_resource_usage({}, "eastus", RESOURCE_ID, lookback_minutes=15)
    assert exc_info.value.code == "AZURE_CREDENTIALS_INCOMPLETE"


def test_fetch_vm_resource_usage_raises_when_no_datapoints():
    empty_response = SimpleNamespace(metrics=[])
    with patch("app.integrations.azure_monitor.ClientSecretCredential"), patch(
        "app.integrations.azure_monitor.MetricsQueryClient"
    ) as mock_client_factory:
        mock_client_factory.return_value.query_resource.return_value = empty_response
        with pytest.raises(ValidationAppError) as exc_info:
            fetch_vm_resource_usage(FAKE_CREDENTIALS, "eastus", RESOURCE_ID, lookback_minutes=15)
    assert exc_info.value.code == "NO_AZURE_MONITOR_DATA"


def test_fetch_vm_resource_usage_wraps_invalid_credentials_cleanly():
    with patch("app.integrations.azure_monitor.ClientSecretCredential"), patch(
        "app.integrations.azure_monitor.MetricsQueryClient"
    ) as mock_client_factory:
        mock_client_factory.return_value.query_resource.side_effect = ClientAuthenticationError(
            "invalid client secret"
        )
        with pytest.raises(ValidationAppError) as exc_info:
            fetch_vm_resource_usage(FAKE_CREDENTIALS, "eastus", RESOURCE_ID, lookback_minutes=15)
    assert exc_info.value.code == "AZURE_MONITOR_REQUEST_FAILED"


def test_fetch_vm_resource_usage_retries_transient_error_then_succeeds():
    now = datetime.now(timezone.utc)
    throttled = HttpResponseError(message="Too many requests")
    throttled.status_code = 429

    with patch("app.integrations.azure_monitor.ClientSecretCredential"), patch(
        "app.integrations.azure_monitor.MetricsQueryClient"
    ) as mock_client_factory:
        mock_client_factory.return_value.query_resource.side_effect = [
            throttled,
            _fake_response(10.0, 0.0, 0.0, now),
        ]
        result = fetch_vm_resource_usage(FAKE_CREDENTIALS, "eastus", RESOURCE_ID, lookback_minutes=15)

    assert result["cpu_usage_percent"] == pytest.approx(10.0)
    assert mock_client_factory.return_value.query_resource.call_count == 2


def test_fetch_vm_resource_usage_does_not_retry_non_transient_error():
    rejected = HttpResponseError(message="Forbidden")
    rejected.status_code = 403

    with patch("app.integrations.azure_monitor.ClientSecretCredential"), patch(
        "app.integrations.azure_monitor.MetricsQueryClient"
    ) as mock_client_factory:
        mock_client_factory.return_value.query_resource.side_effect = rejected
        with pytest.raises(ValidationAppError):
            fetch_vm_resource_usage(FAKE_CREDENTIALS, "eastus", RESOURCE_ID, lookback_minutes=15)

    assert mock_client_factory.return_value.query_resource.call_count == 1


def test_fetch_vm_resource_usage_wraps_unreachable_service():
    with patch("app.integrations.azure_monitor.ClientSecretCredential"), patch(
        "app.integrations.azure_monitor.MetricsQueryClient"
    ) as mock_client_factory:
        mock_client_factory.return_value.query_resource.side_effect = ServiceRequestError(
            "connection refused"
        )
        with pytest.raises(ValidationAppError) as exc_info:
            fetch_vm_resource_usage(FAKE_CREDENTIALS, "eastus", RESOURCE_ID, lookback_minutes=15)
    assert exc_info.value.code == "AZURE_MONITOR_REQUEST_FAILED"
