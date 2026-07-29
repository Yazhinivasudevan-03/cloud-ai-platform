"""Unit tests for Phase 25B's Alibaba Cloud CloudProviderClient adapter.
There is no Alibaba Cloud emulator available and no live account to
validate against (see alibaba_provider.py's own docstring), so - exactly
like test_oci_provider.py - this patches the real Tea-based SDK client
classes directly rather than exercising a real request/response round
trip."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from Tea.exceptions import TeaException

from app.integrations.providers.alibaba_provider import AlibabaCloudProviderClient
from app.utils.exceptions import ValidationAppError

FAKE_CREDENTIALS = {"access_key_id": "fake-ak", "access_key_secret": "fake-sk"}
INSTANCE_ID = "i-fakeinstance123"


def _fake_region(region_id: str, local_name: str) -> SimpleNamespace:
    return SimpleNamespace(region_id=region_id, local_name=local_name)


def _fake_regions_response(*regions: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(body=SimpleNamespace(regions=SimpleNamespace(region=list(regions))))


def _fake_metric_response(*values: float) -> SimpleNamespace:
    datapoints = json.dumps([{"Average": v} for v in values])
    return SimpleNamespace(body=SimpleNamespace(datapoints=datapoints))


# --- list_regions -----------------------------------------------------


@patch("app.integrations.providers.alibaba_provider.EcsClient")
def test_list_regions_parses_a_realistic_response(mock_client_cls):
    mock_client_cls.return_value.describe_regions.return_value = _fake_regions_response(
        _fake_region("cn-hangzhou", "China (Hangzhou)"),
        _fake_region("ap-southeast-1", "Singapore"),
    )
    client = AlibabaCloudProviderClient(FAKE_CREDENTIALS, "cn-hangzhou")

    regions = client.list_regions()

    assert regions == [
        {"id": "cn-hangzhou", "display_name": "China (Hangzhou)"},
        {"id": "ap-southeast-1", "display_name": "Singapore"},
    ]


def test_list_regions_requires_credentials():
    client = AlibabaCloudProviderClient({}, "cn-hangzhou")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "ALIBABA_CREDENTIALS_INCOMPLETE"


@patch("app.integrations.providers.alibaba_provider.EcsClient")
def test_list_regions_wraps_a_rejected_request(mock_client_cls):
    mock_client_cls.return_value.describe_regions.side_effect = TeaException(
        {"code": "InvalidAccessKeyId.NotFound", "message": "access key not found"}
    )
    client = AlibabaCloudProviderClient(FAKE_CREDENTIALS, "cn-hangzhou")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "ALIBABA_REGION_DISCOVERY_FAILED"


# --- list_monitoring -----------------------------------------------------


@patch("app.integrations.providers.alibaba_provider.CmsClient")
def test_list_monitoring_parses_a_realistic_response(mock_client_cls):
    mock_client_cls.return_value.describe_metric_last.side_effect = [
        _fake_metric_response(42.5),
        _fake_metric_response(8000.0),  # bit/sec
        _fake_metric_response(4000.0),
    ]
    client = AlibabaCloudProviderClient(FAKE_CREDENTIALS, "cn-hangzhou")

    result = client.list_monitoring(INSTANCE_ID, lookback_minutes=15)

    assert result["cpu_usage_percent"] == pytest.approx(42.5)
    assert result["network_in_kbps"] == pytest.approx(8.0)
    assert result["network_out_kbps"] == pytest.approx(4.0)
    assert result["memory_usage_mb"] == 0.0
    assert result["disk_usage_mb"] == 0.0


@patch("app.integrations.providers.alibaba_provider.CmsClient")
def test_list_monitoring_raises_when_no_datapoints(mock_client_cls):
    mock_client_cls.return_value.describe_metric_last.return_value = SimpleNamespace(
        body=SimpleNamespace(datapoints="[]")
    )
    client = AlibabaCloudProviderClient(FAKE_CREDENTIALS, "cn-hangzhou")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_monitoring(INSTANCE_ID, lookback_minutes=15)
    assert exc_info.value.code == "NO_ALIBABA_MONITORING_DATA"


@patch("app.integrations.providers.alibaba_provider.CmsClient")
def test_list_monitoring_wraps_a_rejected_request(mock_client_cls):
    mock_client_cls.return_value.describe_metric_last.side_effect = TeaException(
        {"code": "InvalidParameter", "message": "bad dimensions"}
    )
    client = AlibabaCloudProviderClient(FAKE_CREDENTIALS, "cn-hangzhou")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_monitoring(INSTANCE_ID, lookback_minutes=15)
    assert exc_info.value.code == "ALIBABA_MONITORING_REQUEST_FAILED"


def test_provider_name_is_alibaba():
    assert AlibabaCloudProviderClient(FAKE_CREDENTIALS, "cn-hangzhou").provider_name == "alibaba"
