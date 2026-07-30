"""Unit tests for Phase 28's IBM Cloud Usage Reports billing integration -
patches the real `ibm_platform_services` SDK clients directly (no IBM
Cloud emulator available)."""
from unittest.mock import MagicMock, patch

import pytest
from ibm_cloud_sdk_core.api_exception import ApiException

from app.integrations.ibm_usage_reports import fetch_monthly_costs_by_service
from app.utils.exceptions import ValidationAppError

CREDENTIALS = {"api_key": "fake-api-key"}


def _detailed_response(result: dict) -> MagicMock:
    response = MagicMock()
    response.get_result.return_value = result
    return response


def test_fetch_monthly_costs_by_service_requires_credentials():
    with pytest.raises(ValidationAppError) as exc_info:
        fetch_monthly_costs_by_service({}, months=1)
    assert exc_info.value.code == "IBM_CREDENTIALS_INCOMPLETE"


@patch("app.integrations.ibm_usage_reports.ibm_platform_services.UsageReportsV4")
@patch("app.integrations.ibm_usage_reports.ibm_platform_services.IamIdentityV1")
def test_fetch_monthly_costs_by_service_parses_a_realistic_response(mock_iam_cls, mock_usage_cls):
    mock_iam_cls.return_value.get_api_keys_details.return_value = _detailed_response(
        {"account_id": "fake-account-id"}
    )
    mock_usage_cls.return_value.get_account_usage.return_value = _detailed_response(
        {
            "currency_code": "USD",
            "resources": [
                {"resource_id": "is.instance", "resource_name": "Virtual Server for VPC", "billable_cost": 42.5},
                {"resource_id": "cloud-object-storage", "resource_name": "Cloud Object Storage", "billable_cost": 0.0},
            ],
        }
    )

    results = fetch_monthly_costs_by_service(CREDENTIALS, months=1)

    assert len(results) == 1  # the zero-cost resource is skipped
    assert results[0]["service_name"] == "Virtual Server for VPC"
    assert results[0]["cost_amount"] == pytest.approx(42.5)
    assert results[0]["currency"] == "USD"


@patch("app.integrations.ibm_usage_reports.ibm_platform_services.UsageReportsV4")
@patch("app.integrations.ibm_usage_reports.ibm_platform_services.IamIdentityV1")
def test_fetch_monthly_costs_by_service_skips_a_month_with_no_usage_report_yet(mock_iam_cls, mock_usage_cls):
    mock_iam_cls.return_value.get_api_keys_details.return_value = _detailed_response(
        {"account_id": "fake-account-id"}
    )
    mock_usage_cls.return_value.get_account_usage.side_effect = ApiException(404, message="not found")

    results = fetch_monthly_costs_by_service(CREDENTIALS, months=2)

    assert results == []


@patch("app.integrations.ibm_usage_reports.ibm_platform_services.IamIdentityV1")
def test_fetch_monthly_costs_by_service_reports_a_rejected_account_lookup(mock_iam_cls):
    mock_iam_cls.return_value.get_api_keys_details.side_effect = ApiException(400, message="invalid api key")

    with pytest.raises(ValidationAppError) as exc_info:
        fetch_monthly_costs_by_service(CREDENTIALS, months=1)
    assert exc_info.value.code == "IBM_CREDENTIALS_REJECTED"


@patch("app.integrations.ibm_usage_reports.ibm_platform_services.UsageReportsV4")
@patch("app.integrations.ibm_usage_reports.ibm_platform_services.IamIdentityV1")
def test_fetch_monthly_costs_by_service_wraps_a_rejected_usage_request(mock_iam_cls, mock_usage_cls):
    mock_iam_cls.return_value.get_api_keys_details.return_value = _detailed_response(
        {"account_id": "fake-account-id"}
    )
    mock_usage_cls.return_value.get_account_usage.side_effect = ApiException(403, message="not authorized")

    with pytest.raises(ValidationAppError) as exc_info:
        fetch_monthly_costs_by_service(CREDENTIALS, months=1)
    assert exc_info.value.code == "IBM_USAGE_REPORTS_REQUEST_FAILED"
