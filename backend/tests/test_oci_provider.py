"""Unit tests for Phase 25B's OCI CloudProviderClient adapter. There is no
OCI emulator available and no live tenancy to validate against (see
oci_provider.py's own docstring), so - exactly like test_azure_monitor.py/
test_gcp_monitoring.py - this patches the real `oci` SDK client classes
directly rather than exercising a real request/response round trip."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from oci.exceptions import ServiceError

from app.integrations.providers.oci_provider import OciCloudProviderClient
from app.utils.exceptions import ValidationAppError

FAKE_CREDENTIALS = {
    "user": "ocid1.user.oc1..fake",
    "tenancy": "ocid1.tenancy.oc1..fake",
    "fingerprint": "aa:bb:cc:dd",
    "key_content": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
}
INSTANCE_OCID = "ocid1.instance.oc1.iad.fake"


def _fake_subscription(region_name: str, status: str = "READY") -> SimpleNamespace:
    return SimpleNamespace(region_name=region_name, status=status)


def _fake_metric_data(*values: float) -> SimpleNamespace:
    return SimpleNamespace(aggregated_datapoints=[SimpleNamespace(value=v) for v in values])


# --- list_regions -----------------------------------------------------


@patch("app.integrations.providers.oci_provider.oci.identity.IdentityClient")
def test_list_regions_parses_real_subscriptions(mock_client_cls):
    mock_client_cls.return_value.list_region_subscriptions.return_value = SimpleNamespace(
        data=[
            _fake_subscription("us-ashburn-1"),
            _fake_subscription("uk-london-1"),
            _fake_subscription("sa-vinhedo-1", status="PROVISIONING"),  # not yet usable
        ]
    )
    client = OciCloudProviderClient(FAKE_CREDENTIALS, "us-ashburn-1")

    regions = client.list_regions()

    assert regions == [
        {"id": "us-ashburn-1", "display_name": "US East (Ashburn)"},
        {"id": "uk-london-1", "display_name": "UK South (London)"},
    ]


def test_list_regions_requires_full_credentials():
    client = OciCloudProviderClient({"user": "x"}, "us-ashburn-1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "OCI_CREDENTIALS_INCOMPLETE"


@patch("app.integrations.providers.oci_provider.oci.identity.IdentityClient")
def test_list_regions_wraps_a_rejected_request(mock_client_cls):
    mock_client_cls.return_value.list_region_subscriptions.side_effect = ServiceError(
        401, "NotAuthenticated", {}, "The required information to complete authentication was not provided"
    )
    client = OciCloudProviderClient(FAKE_CREDENTIALS, "us-ashburn-1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "OCI_REGION_CREDENTIALS_REJECTED"


@patch("app.integrations.providers.oci_provider.oci.identity.IdentityClient")
def test_list_regions_reports_access_denied(mock_client_cls):
    mock_client_cls.return_value.list_region_subscriptions.side_effect = ServiceError(
        403, "NotAuthorized", {}, "not authorized"
    )
    client = OciCloudProviderClient(FAKE_CREDENTIALS, "us-ashburn-1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "OCI_REGION_ACCESS_DENIED"


@patch("app.integrations.providers.oci_provider.oci.identity.IdentityClient")
def test_list_regions_reports_throttled_after_retries_exhausted(mock_client_cls):
    mock_client_cls.return_value.list_region_subscriptions.side_effect = ServiceError(
        429, "TooManyRequests", {}, "slow down"
    )
    client = OciCloudProviderClient(FAKE_CREDENTIALS, "us-ashburn-1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "OCI_REGION_THROTTLED"
    assert mock_client_cls.return_value.list_region_subscriptions.call_count == 3


@patch("app.integrations.providers.oci_provider.oci.identity.IdentityClient")
def test_list_regions_reports_provider_outage(mock_client_cls):
    mock_client_cls.return_value.list_region_subscriptions.side_effect = ServiceError(
        500, "InternalServerError", {}, "internal error"
    )
    client = OciCloudProviderClient(FAKE_CREDENTIALS, "us-ashburn-1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "OCI_REGION_PROVIDER_OUTAGE"


@patch("app.integrations.providers.oci_provider.oci.identity.IdentityClient")
def test_list_regions_reports_no_regions_returned(mock_client_cls):
    mock_client_cls.return_value.list_region_subscriptions.return_value = SimpleNamespace(data=[])
    client = OciCloudProviderClient(FAKE_CREDENTIALS, "us-ashburn-1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "OCI_REGION_NO_REGIONS_RETURNED"


# --- list_monitoring -----------------------------------------------------


@patch("app.integrations.providers.oci_provider.oci.monitoring.MonitoringClient")
def test_list_monitoring_parses_a_realistic_response(mock_client_cls):
    mock_client_cls.return_value.summarize_metrics_data.side_effect = [
        SimpleNamespace(data=[_fake_metric_data(42.5)]),
        SimpleNamespace(data=[_fake_metric_data(1000.0)]),  # bytes/sec
        SimpleNamespace(data=[_fake_metric_data(500.0)]),
    ]
    client = OciCloudProviderClient(FAKE_CREDENTIALS, "us-ashburn-1")

    result = client.list_monitoring(INSTANCE_OCID, lookback_minutes=15)

    assert result["cpu_usage_percent"] == pytest.approx(42.5)
    assert result["network_in_kbps"] == pytest.approx(8.0)
    assert result["network_out_kbps"] == pytest.approx(4.0)
    assert result["memory_usage_mb"] == 0.0
    assert result["disk_usage_mb"] == 0.0


@patch("app.integrations.providers.oci_provider.oci.monitoring.MonitoringClient")
def test_list_monitoring_raises_when_no_datapoints(mock_client_cls):
    mock_client_cls.return_value.summarize_metrics_data.return_value = SimpleNamespace(data=[])
    client = OciCloudProviderClient(FAKE_CREDENTIALS, "us-ashburn-1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_monitoring(INSTANCE_OCID, lookback_minutes=15)
    assert exc_info.value.code == "NO_OCI_MONITORING_DATA"


@patch("app.integrations.providers.oci_provider.oci.monitoring.MonitoringClient")
def test_list_monitoring_wraps_a_rejected_request(mock_client_cls):
    mock_client_cls.return_value.summarize_metrics_data.side_effect = ServiceError(
        404, "NotFound", {}, "compartment not found"
    )
    client = OciCloudProviderClient(FAKE_CREDENTIALS, "us-ashburn-1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_monitoring(INSTANCE_OCID, lookback_minutes=15)
    assert exc_info.value.code == "OCI_MONITORING_REQUEST_FAILED"


def test_provider_name_is_oci():
    assert OciCloudProviderClient(FAKE_CREDENTIALS, "us-ashburn-1").provider_name == "oci"
