"""Unit tests for Phase 28's DigitalOcean billing integration - patches the
real `pydo` SDK client directly (no DigitalOcean emulator available)."""
from unittest.mock import patch

import pytest
from azure.core.exceptions import HttpResponseError

from app.integrations.digitalocean_billing import fetch_monthly_costs_by_service
from app.utils.exceptions import ValidationAppError

CREDENTIALS = {"api_token": "fake-token"}


def test_fetch_monthly_costs_by_service_requires_credentials():
    with pytest.raises(ValidationAppError) as exc_info:
        fetch_monthly_costs_by_service({}, months=3)
    assert exc_info.value.code == "DIGITALOCEAN_CREDENTIALS_INCOMPLETE"


@patch("app.integrations.digitalocean_billing.pydo.Client")
def test_fetch_monthly_costs_by_service_parses_and_groups_by_product(mock_client_cls):
    mock_client_cls.return_value.invoices.list.return_value = {
        "invoices": [{"invoice_uuid": "uuid-1", "invoice_period": "2026-06"}]
    }
    mock_client_cls.return_value.invoices.get_by_uuid.return_value = {
        "invoice_items": [
            {"product": "Droplets", "amount": "12.50"},
            {"product": "Droplets", "amount": "7.50"},
            {"product": "Spaces", "amount": "5.00"},
            {"product": "Free Credits", "amount": "0.00"},
        ]
    }

    results = fetch_monthly_costs_by_service(CREDENTIALS, months=3)

    by_service = {r["service_name"]: r["cost_amount"] for r in results}
    assert by_service["Droplets"] == pytest.approx(20.0)
    assert by_service["Spaces"] == pytest.approx(5.0)
    assert "Free Credits" not in by_service  # zero-cost items are skipped
    assert all(r["currency"] == "USD" for r in results)
    assert all(r["billing_period_start"].isoformat() == "2026-06-01" for r in results)


@patch("app.integrations.digitalocean_billing.pydo.Client")
def test_fetch_monthly_costs_by_service_only_fetches_the_requested_number_of_months(mock_client_cls):
    mock_client_cls.return_value.invoices.list.return_value = {
        "invoices": [
            {"invoice_uuid": "uuid-1", "invoice_period": "2026-06"},
            {"invoice_uuid": "uuid-2", "invoice_period": "2026-05"},
            {"invoice_uuid": "uuid-3", "invoice_period": "2026-04"},
        ]
    }
    mock_client_cls.return_value.invoices.get_by_uuid.return_value = {"invoice_items": []}

    fetch_monthly_costs_by_service(CREDENTIALS, months=2)

    assert mock_client_cls.return_value.invoices.get_by_uuid.call_count == 2


@patch("app.integrations.digitalocean_billing.pydo.Client")
def test_fetch_monthly_costs_by_service_wraps_a_rejected_request(mock_client_cls):
    error = HttpResponseError(message="unauthorized")
    error.status_code = 401
    mock_client_cls.return_value.invoices.list.side_effect = error

    with pytest.raises(ValidationAppError) as exc_info:
        fetch_monthly_costs_by_service(CREDENTIALS, months=3)
    assert exc_info.value.code == "DIGITALOCEAN_BILLING_REQUEST_FAILED"
