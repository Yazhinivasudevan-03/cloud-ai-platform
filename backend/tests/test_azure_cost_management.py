"""Unit tests for the real Azure Cost Management integration - patches the
`azure-mgmt-costmanagement` SDK client directly (no Azure emulator
available), mirroring the patched-client half of test_aws_cost_explorer.py."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError, ServiceRequestError

from app.integrations.azure_cost_management import fetch_monthly_costs_by_service
from app.utils.exceptions import ValidationAppError

FAKE_CREDENTIALS = {
    "tenant_id": "fake-tenant",
    "client_id": "fake-client",
    "client_secret": "fake-secret",
    "subscription_id": "fake-sub",
}


def _fake_query_response():
    columns = [
        SimpleNamespace(name="Cost"),
        SimpleNamespace(name="ServiceName"),
        SimpleNamespace(name="BillingMonth"),
        SimpleNamespace(name="Currency"),
    ]
    rows = [
        [123.45, "Virtual Machines", 20260501, "USD"],
        [0.0, "Storage", 20260501, "USD"],  # zero-cost - must be skipped
        [150.0, "Virtual Machines", 20260601, "USD"],
    ]
    return SimpleNamespace(columns=columns, rows=rows)


def test_fetch_monthly_costs_parses_a_realistic_response_and_skips_zero_cost_services():
    with patch("app.integrations.azure_cost_management.ClientSecretCredential"), patch(
        "app.integrations.azure_cost_management.CostManagementClient"
    ) as mock_client_factory:
        mock_client_factory.return_value.query.usage.return_value = _fake_query_response()
        result = fetch_monthly_costs_by_service(FAKE_CREDENTIALS, months=2)

    assert len(result) == 2  # the $0.00 Storage entry must be skipped
    may_entry = next(r for r in result if r["billing_period_start"].isoformat() == "2026-05-01")
    assert may_entry["service_name"] == "Virtual Machines"
    assert may_entry["cost_amount"] == pytest.approx(123.45)
    assert may_entry["currency"] == "USD"
    assert may_entry["billing_period_end"].isoformat() == "2026-05-31"

    june_entry = next(r for r in result if r["billing_period_start"].isoformat() == "2026-06-01")
    assert june_entry["cost_amount"] == pytest.approx(150.0)


def test_fetch_monthly_costs_requires_full_credentials():
    with pytest.raises(ValidationAppError) as exc_info:
        fetch_monthly_costs_by_service({"tenant_id": "t"}, months=3)
    assert exc_info.value.code == "AZURE_CREDENTIALS_INCOMPLETE"


def test_fetch_monthly_costs_raises_cleanly_on_missing_expected_column():
    bad_response = SimpleNamespace(
        columns=[SimpleNamespace(name="SomethingUnexpected")], rows=[]
    )
    with patch("app.integrations.azure_cost_management.ClientSecretCredential"), patch(
        "app.integrations.azure_cost_management.CostManagementClient"
    ) as mock_client_factory:
        mock_client_factory.return_value.query.usage.return_value = bad_response
        with pytest.raises(ValidationAppError) as exc_info:
            fetch_monthly_costs_by_service(FAKE_CREDENTIALS, months=1)
    assert exc_info.value.code == "AZURE_COST_MANAGEMENT_UNEXPECTED_RESPONSE"


def test_fetch_monthly_costs_wraps_invalid_credentials_cleanly():
    with patch("app.integrations.azure_cost_management.ClientSecretCredential"), patch(
        "app.integrations.azure_cost_management.CostManagementClient"
    ) as mock_client_factory:
        mock_client_factory.return_value.query.usage.side_effect = ClientAuthenticationError(
            "invalid client secret"
        )
        with pytest.raises(ValidationAppError) as exc_info:
            fetch_monthly_costs_by_service(FAKE_CREDENTIALS, months=1)
    assert exc_info.value.code == "AZURE_COST_MANAGEMENT_REQUEST_FAILED"


def test_fetch_monthly_costs_retries_transient_error_then_succeeds():
    throttled = HttpResponseError(message="Too many requests")
    throttled.status_code = 429

    with patch("app.integrations.azure_cost_management.ClientSecretCredential"), patch(
        "app.integrations.azure_cost_management.CostManagementClient"
    ) as mock_client_factory:
        mock_client_factory.return_value.query.usage.side_effect = [
            throttled,
            _fake_query_response(),
        ]
        result = fetch_monthly_costs_by_service(FAKE_CREDENTIALS, months=2)

    assert len(result) == 2
    assert mock_client_factory.return_value.query.usage.call_count == 2


def test_fetch_monthly_costs_does_not_retry_non_transient_error():
    rejected = HttpResponseError(message="Forbidden")
    rejected.status_code = 403

    with patch("app.integrations.azure_cost_management.ClientSecretCredential"), patch(
        "app.integrations.azure_cost_management.CostManagementClient"
    ) as mock_client_factory:
        mock_client_factory.return_value.query.usage.side_effect = rejected
        with pytest.raises(ValidationAppError):
            fetch_monthly_costs_by_service(FAKE_CREDENTIALS, months=1)

    assert mock_client_factory.return_value.query.usage.call_count == 1


def test_fetch_monthly_costs_wraps_unreachable_service():
    with patch("app.integrations.azure_cost_management.ClientSecretCredential"), patch(
        "app.integrations.azure_cost_management.CostManagementClient"
    ) as mock_client_factory:
        mock_client_factory.return_value.query.usage.side_effect = ServiceRequestError(
            "connection refused"
        )
        with pytest.raises(ValidationAppError) as exc_info:
            fetch_monthly_costs_by_service(FAKE_CREDENTIALS, months=1)
    assert exc_info.value.code == "AZURE_COST_MANAGEMENT_REQUEST_FAILED"
