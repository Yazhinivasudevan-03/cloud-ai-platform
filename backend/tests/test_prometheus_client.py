"""Unit tests for app.integrations.prometheus_client (Phase 23) - mocks
httpx so these run without a real Prometheus instance reachable."""
from unittest.mock import MagicMock, patch

from app.integrations import prometheus_client


def _mock_response(value: str | None):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "data": {"result": [] if value is None else [{"value": [0, value]}]}
    }
    return response


def test_average_latency_ms_returns_none_with_no_traffic():
    with patch("httpx.get", return_value=_mock_response(None)):
        assert prometheus_client.average_latency_ms() is None


def test_average_latency_ms_computes_from_sum_and_count():
    responses = [_mock_response("2.0"), _mock_response("0.5")]  # count=2, sum=0.5s
    with patch("httpx.get", side_effect=responses):
        result = prometheus_client.average_latency_ms()
    assert result == 250.0  # (0.5 / 2) * 1000ms


def test_error_rate_percent_returns_none_with_no_traffic():
    with patch("httpx.get", return_value=_mock_response(None)):
        assert prometheus_client.error_rate_percent() is None


def test_error_rate_percent_is_zero_with_traffic_but_no_errors():
    responses = [_mock_response("10.0"), _mock_response(None)]  # total=10/s, no 5xx series at all
    with patch("httpx.get", side_effect=responses):
        result = prometheus_client.error_rate_percent()
    assert result == 0.0


def test_error_rate_percent_computes_a_real_ratio():
    responses = [_mock_response("10.0"), _mock_response("2.0")]  # 2/10 = 20%
    with patch("httpx.get", side_effect=responses):
        result = prometheus_client.error_rate_percent()
    assert result == 20.0


def test_instant_query_returns_none_when_prometheus_is_unreachable():
    with patch("httpx.get", side_effect=ConnectionError("no route to host")):
        assert prometheus_client.average_latency_ms() is None
        assert prometheus_client.error_rate_percent() is None
