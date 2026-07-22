"""Unit tests for the real AWS Cost Explorer integration.

moto's Cost Explorer emulation has no way to seed cost data (real AWS has
no API to inject billing data either - it's generated internally from
actual usage), so moto-backed tests here only verify the real wiring
(genuine boto3 calls, genuine request/response serialization, credential
validation) succeeds and returns a clean empty result rather than raising.
Parsing logic for a populated response is verified separately against a
patched boto3 client returning a realistic fixture response, mirroring
the same dual approach used in test_aws_cloudwatch.py."""
from unittest.mock import patch

import boto3
import botocore.exceptions
import pytest
from moto import mock_aws

from app.integrations.aws_cost_explorer import fetch_monthly_costs_by_service
from app.utils.exceptions import ValidationAppError

FAKE_CREDENTIALS = {"access_key_id": "testing", "secret_access_key": "testing"}


@mock_aws
def test_fetch_monthly_costs_makes_a_real_call_and_returns_cleanly():
    # moto's CE backend has no cost data to report for a fresh fake
    # account - this proves the real boto3 client/request wiring (region,
    # credentials, TimePeriod, GroupBy) is well-formed and doesn't error,
    # not that it returns non-empty data (which moto cannot provide here).
    result = fetch_monthly_costs_by_service(FAKE_CREDENTIALS, months=3)
    assert result == []


def test_fetch_monthly_costs_requires_access_key_and_secret():
    with pytest.raises(ValidationAppError) as exc_info:
        fetch_monthly_costs_by_service({}, months=3)
    assert exc_info.value.code == "AWS_CREDENTIALS_INCOMPLETE"


def _fake_cost_and_usage_response() -> dict:
    return {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": "2026-05-01", "End": "2026-06-01"},
                "Groups": [
                    {
                        "Keys": ["Amazon Elastic Compute Cloud - Compute"],
                        "Metrics": {"UnblendedCost": {"Amount": "123.45", "Unit": "USD"}},
                    },
                    {
                        "Keys": ["Amazon Simple Storage Service"],
                        "Metrics": {"UnblendedCost": {"Amount": "0.00", "Unit": "USD"}},
                    },
                ],
            },
            {
                "TimePeriod": {"Start": "2026-06-01", "End": "2026-07-01"},
                "Groups": [
                    {
                        "Keys": ["Amazon Elastic Compute Cloud - Compute"],
                        "Metrics": {"UnblendedCost": {"Amount": "150.00", "Unit": "USD"}},
                    },
                ],
            },
        ]
    }


def test_fetch_monthly_costs_parses_a_realistic_response_and_skips_zero_cost_services():
    with patch("boto3.client") as mock_client_factory:
        mock_client_factory.return_value.get_cost_and_usage.return_value = (
            _fake_cost_and_usage_response()
        )
        result = fetch_monthly_costs_by_service(FAKE_CREDENTIALS, months=2)

    assert len(result) == 2  # the $0.00 S3 entry must be skipped
    ec2_may = next(r for r in result if r["billing_period_start"].isoformat() == "2026-05-01")
    assert ec2_may["service_name"] == "Amazon Elastic Compute Cloud - Compute"
    assert ec2_may["cost_amount"] == pytest.approx(123.45)
    assert ec2_may["currency"] == "USD"
    assert ec2_may["billing_period_end"].isoformat() == "2026-05-31"  # End is exclusive, minus 1 day

    ec2_june = next(r for r in result if r["billing_period_start"].isoformat() == "2026-06-01")
    assert ec2_june["cost_amount"] == pytest.approx(150.00)


def test_fetch_monthly_costs_wraps_invalid_credentials_cleanly():
    error_response = {"Error": {"Code": "AuthFailure", "Message": "AWS was not able to validate the provided access credentials"}}
    client_error = botocore.exceptions.ClientError(error_response, "GetCostAndUsage")

    with patch("boto3.client") as mock_client_factory:
        mock_client_factory.return_value.get_cost_and_usage.side_effect = client_error
        with pytest.raises(ValidationAppError) as exc_info:
            fetch_monthly_costs_by_service(FAKE_CREDENTIALS, months=1)

    assert exc_info.value.code == "COST_EXPLORER_REQUEST_FAILED"
    assert "AuthFailure" in str(exc_info.value)


def test_fetch_monthly_costs_retries_transient_error_then_succeeds():
    error_response = {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}
    throttling_error = botocore.exceptions.ClientError(error_response, "GetCostAndUsage")

    with patch("boto3.client") as mock_client_factory:
        mock_client_factory.return_value.get_cost_and_usage.side_effect = [
            throttling_error,
            _fake_cost_and_usage_response(),
        ]
        result = fetch_monthly_costs_by_service(FAKE_CREDENTIALS, months=2)

    assert len(result) == 2
    assert mock_client_factory.return_value.get_cost_and_usage.call_count == 2


def test_fetch_monthly_costs_does_not_retry_non_transient_client_error():
    error_response = {"Error": {"Code": "AuthFailure", "Message": "bad credentials"}}
    client_error = botocore.exceptions.ClientError(error_response, "GetCostAndUsage")

    with patch("boto3.client") as mock_client_factory:
        mock_client_factory.return_value.get_cost_and_usage.side_effect = client_error
        with pytest.raises(ValidationAppError):
            fetch_monthly_costs_by_service(FAKE_CREDENTIALS, months=1)

    assert mock_client_factory.return_value.get_cost_and_usage.call_count == 1
