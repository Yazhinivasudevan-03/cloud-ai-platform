"""Unit tests for Phase 28's DigitalOcean Droplet metrics integration -
patches the real `pydo` SDK client directly, the same pattern already
established for every DigitalOcean/IBM/OCI/Alibaba integration in this
project (no DigitalOcean emulator available)."""
from unittest.mock import patch

import pytest
from azure.core.exceptions import HttpResponseError

from app.integrations.digitalocean_monitoring import fetch_droplet_resource_usage
from app.utils.exceptions import ValidationAppError

CREDENTIALS = {"api_token": "fake-token"}


def _matrix_response(*, mode_values: dict[str, float] | None = None, plain_value: float | None = None) -> dict:
    if mode_values is not None:
        return {
            "data": {
                "result": [
                    {"metric": {"mode": mode}, "values": [["1700000000", str(value)]]}
                    for mode, value in mode_values.items()
                ]
            }
        }
    if plain_value is not None:
        return {"data": {"result": [{"metric": {}, "values": [["1700000000", str(plain_value)]]}]}}
    return {"data": {"result": []}}


def test_fetch_droplet_resource_usage_requires_credentials():
    with pytest.raises(ValidationAppError) as exc_info:
        fetch_droplet_resource_usage({}, "nyc1", "123", lookback_minutes=15)
    assert exc_info.value.code == "DIGITALOCEAN_CREDENTIALS_INCOMPLETE"


@patch("app.integrations.digitalocean_monitoring.pydo.Client")
def test_fetch_droplet_resource_usage_parses_a_realistic_response(mock_client_cls):
    monitoring = mock_client_cls.return_value.monitoring
    monitoring.get_droplet_cpu_metrics.return_value = _matrix_response(
        mode_values={"idle": 75.0, "user": 20.0, "system": 5.0}
    )
    monitoring.get_droplet_memory_total_metrics.return_value = _matrix_response(plain_value=1_073_741_824)  # 1 GiB
    monitoring.get_droplet_memory_available_metrics.return_value = _matrix_response(plain_value=536_870_912)  # 0.5 GiB
    monitoring.get_droplet_filesystem_size_metrics.return_value = _matrix_response(plain_value=10_737_418_240)  # 10 GiB
    monitoring.get_droplet_filesystem_free_metrics.return_value = _matrix_response(plain_value=8_589_934_592)  # 8 GiB
    monitoring.get_droplet_bandwidth_metrics.return_value = _matrix_response(plain_value=2.0)  # 2 Mbps

    result = fetch_droplet_resource_usage(CREDENTIALS, "nyc1", "123", lookback_minutes=15)

    assert result["cpu_usage_percent"] == pytest.approx(25.0)  # 100 - idle(75)
    assert result["memory_usage_mb"] == pytest.approx(512.0, rel=0.01)  # (1GiB - 0.5GiB) in MB
    assert result["disk_usage_mb"] == pytest.approx(2048.0, rel=0.01)  # (10GiB - 8GiB) in MB
    assert result["network_in_kbps"] == pytest.approx(2000.0)  # 2 Mbps -> 2000 kbps
    assert result["network_out_kbps"] == pytest.approx(2000.0)


@patch("app.integrations.digitalocean_monitoring.pydo.Client")
def test_fetch_droplet_resource_usage_falls_back_when_no_idle_series(mock_client_cls):
    monitoring = mock_client_cls.return_value.monitoring
    monitoring.get_droplet_cpu_metrics.return_value = _matrix_response(mode_values={"user": 10.0, "system": 5.0})
    monitoring.get_droplet_memory_total_metrics.return_value = _matrix_response()
    monitoring.get_droplet_memory_available_metrics.return_value = _matrix_response()
    monitoring.get_droplet_filesystem_size_metrics.return_value = _matrix_response()
    monitoring.get_droplet_filesystem_free_metrics.return_value = _matrix_response()
    monitoring.get_droplet_bandwidth_metrics.return_value = _matrix_response()

    result = fetch_droplet_resource_usage(CREDENTIALS, "nyc1", "123", lookback_minutes=15)

    assert result["cpu_usage_percent"] == pytest.approx(15.0)  # sum of non-idle series
    assert result["memory_usage_mb"] == 0.0
    assert result["disk_usage_mb"] == 0.0


@patch("app.integrations.digitalocean_monitoring.pydo.Client")
def test_fetch_droplet_resource_usage_reports_no_data(mock_client_cls):
    monitoring = mock_client_cls.return_value.monitoring
    for method in (
        "get_droplet_cpu_metrics",
        "get_droplet_memory_total_metrics",
        "get_droplet_memory_available_metrics",
        "get_droplet_filesystem_size_metrics",
        "get_droplet_filesystem_free_metrics",
        "get_droplet_bandwidth_metrics",
    ):
        getattr(monitoring, method).return_value = _matrix_response()

    with pytest.raises(ValidationAppError) as exc_info:
        fetch_droplet_resource_usage(CREDENTIALS, "nyc1", "123", lookback_minutes=15)
    assert exc_info.value.code == "NO_DIGITALOCEAN_MONITORING_DATA"


@patch("app.integrations.digitalocean_monitoring.pydo.Client")
def test_fetch_droplet_resource_usage_wraps_a_rejected_request(mock_client_cls):
    error = HttpResponseError(message="not found")
    error.status_code = 404
    mock_client_cls.return_value.monitoring.get_droplet_cpu_metrics.side_effect = error

    with pytest.raises(ValidationAppError) as exc_info:
        fetch_droplet_resource_usage(CREDENTIALS, "nyc1", "123", lookback_minutes=15)
    assert exc_info.value.code == "DIGITALOCEAN_MONITORING_REQUEST_FAILED"
