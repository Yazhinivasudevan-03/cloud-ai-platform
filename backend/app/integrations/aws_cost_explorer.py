"""Real AWS Cost Explorer integration: fetches genuine monthly billing data
grouped by service, for a CloudProviderAccount, replacing manually-entered
CloudCost rows with actual AWS spend (Phase 18, audit roadmap item 9).

Cost Explorer is a global, account-wide API - always queried against the
`us-east-1` endpoint regardless of the account's own configured `region`,
per AWS's own requirement (Cost Explorer has no regional variants), and it
reports spend across the whole AWS account, not scoped to any one
resource. That means the numbers returned here are the account's total
spend by service, stored against whichever project the caller chose to
sync into - the same "one project roughly maps to one account's spend"
assumption already implicit in the pre-existing manual CloudCostCreate
ingestion endpoint.

Only complete past calendar months are fetched (never the current,
still-accruing month) since AWS explicitly flags in-progress month data as
an estimate, and this platform's CloudCost model has no field to represent
"estimated" vs. "final" - a genuine limitation being worked around by
simply not fetching numbers AWS itself would call provisional.
"""
from datetime import date, timedelta
from typing import TypedDict

import boto3
import botocore.exceptions
import tenacity

from app.utils.exceptions import ValidationAppError

# Retries only genuinely transient failures, matching the same policy as
# app/integrations/aws_cloudwatch.py.
_RETRYABLE_CLIENT_ERROR_CODES = {
    "ThrottlingException",
    "RequestLimitExceeded",
    "TooManyRequestsException",
    "ServiceUnavailable",
    "InternalError",
    "RequestTimeout",
}


def _is_retryable_aws_error(exc: BaseException) -> bool:
    if isinstance(exc, botocore.exceptions.ClientError):
        return exc.response.get("Error", {}).get("Code") in _RETRYABLE_CLIENT_ERROR_CODES
    return isinstance(exc, botocore.exceptions.BotoCoreError)


_cost_explorer_retry = tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable_aws_error),
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)


class MonthlyServiceCost(TypedDict):
    service_name: str
    cost_amount: float
    currency: str
    billing_period_start: date
    billing_period_end: date


def _subtract_months(d: date, months: int) -> date:
    """Returns the first day of the month `months` before `d`'s month."""
    zero_based_month = d.month - 1 - months
    year = d.year + zero_based_month // 12
    month = zero_based_month % 12 + 1
    return date(year, month, 1)


def fetch_monthly_costs_by_service(
    credentials: dict[str, str], months: int
) -> list[MonthlyServiceCost]:
    """Queries real AWS Cost Explorer for the last `months` complete
    calendar months of spend, grouped by AWS service, shaped to match
    CloudCostCreate directly so the caller can hand each entry straight to
    the existing cost-ingestion repository.

    Raises ValidationAppError if credentials are missing required keys, or
    if Cost Explorer rejects the request (bad credentials, Cost Explorer
    not enabled for the account, insufficient IAM permissions, etc.).
    """
    access_key_id = credentials.get("access_key_id")
    secret_access_key = credentials.get("secret_access_key")
    if not access_key_id or not secret_access_key:
        raise ValidationAppError(
            "AWS credentials must include 'access_key_id' and 'secret_access_key'",
            code="AWS_CREDENTIALS_INCOMPLETE",
        )

    client_kwargs: dict[str, str] = {
        "region_name": "us-east-1",
        "aws_access_key_id": access_key_id,
        "aws_secret_access_key": secret_access_key,
    }
    session_token = credentials.get("session_token")
    if session_token:
        client_kwargs["aws_session_token"] = session_token
    # Only ever set for testing against a real API-compatible emulator
    # (moto) - a genuine AWS account never needs this.
    endpoint_url = credentials.get("endpoint_url")
    if endpoint_url:
        client_kwargs["endpoint_url"] = endpoint_url

    client = boto3.client("ce", **client_kwargs)

    period_end = date.today().replace(day=1)  # exclusive - start of the current, still-open month
    period_start = _subtract_months(period_end, months)

    @_cost_explorer_retry
    def _get_cost_and_usage():
        return client.get_cost_and_usage(
            TimePeriod={"Start": period_start.isoformat(), "End": period_end.isoformat()},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )

    try:
        response = _get_cost_and_usage()
    except botocore.exceptions.ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        raise ValidationAppError(
            f"AWS Cost Explorer rejected the request ({error_code}): "
            f"{exc.response.get('Error', {}).get('Message', str(exc))}",
            code="COST_EXPLORER_REQUEST_FAILED",
        ) from exc
    except botocore.exceptions.BotoCoreError as exc:
        raise ValidationAppError(
            f"Could not reach AWS Cost Explorer: {exc}", code="COST_EXPLORER_REQUEST_FAILED"
        ) from exc

    results: list[MonthlyServiceCost] = []
    for time_period_result in response.get("ResultsByTime", []):
        month_start = date.fromisoformat(time_period_result["TimePeriod"]["Start"])
        # Cost Explorer's End is exclusive (first day of the following
        # month) - subtracting a day gives the inclusive last day of the
        # billing period, matching CloudCost.billing_period_end's meaning.
        month_end = date.fromisoformat(time_period_result["TimePeriod"]["End"]) - timedelta(days=1)

        for group in time_period_result.get("Groups", []):
            amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
            if amount <= 0:
                # AWS reports every service dimension it knows about, most
                # at $0 for services the account never used - real spend
                # only, not a wall of zero-cost noise.
                continue
            results.append(
                {
                    "service_name": group["Keys"][0],
                    "cost_amount": amount,
                    "currency": group["Metrics"]["UnblendedCost"]["Unit"],
                    "billing_period_start": month_start,
                    "billing_period_end": month_end,
                }
            )

    return results
