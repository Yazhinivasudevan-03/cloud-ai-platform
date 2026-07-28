"""Real Azure Cost Management integration: fetches genuine monthly billing
data grouped by service, for a CloudProviderAccount, via the Cost
Management Query API - Azure's direct equivalent of AWS Cost Explorer
(app/integrations/aws_cost_explorer.py), which this module mirrors closely.

Only complete past calendar months are fetched (never the current,
still-accruing month), same reasoning as aws_cost_explorer.py.

The Query API returns a generic "columns + rows" table rather than a fixed
JSON shape, so this module looks up each expected column by name rather
than assuming a fixed position - if the response is ever missing a column
this parsing relies on, that's surfaced as a clear error rather than
silently reading the wrong value.
"""
from datetime import date, timedelta
from typing import TypedDict

import tenacity
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError, ServiceRequestError
from azure.identity import ClientSecretCredential
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.costmanagement.models import (
    QueryAggregation,
    QueryDataset,
    QueryDefinition,
    QueryGrouping,
    QueryTimePeriod,
)

from app.utils.exceptions import ValidationAppError

_RETRYABLE_STATUS_CODES = {429, 500, 503}


def _is_retryable_azure_error(exc: BaseException) -> bool:
    if isinstance(exc, HttpResponseError):
        return exc.status_code in _RETRYABLE_STATUS_CODES
    return isinstance(exc, ServiceRequestError)


_cost_management_retry = tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable_azure_error),
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


def _column_index(columns: list, name: str) -> int | None:
    for index, column in enumerate(columns):
        column_name = column.name if hasattr(column, "name") else column.get("name")
        if column_name and column_name.lower() == name.lower():
            return index
    return None


def fetch_monthly_costs_by_service(
    credentials: dict[str, str], months: int
) -> list[MonthlyServiceCost]:
    """Queries real Azure Cost Management for the last `months` complete
    calendar months of spend, grouped by service, shaped to match
    CloudCostCreate directly so the caller can hand each entry straight to
    the existing cost-ingestion repository.

    Raises ValidationAppError if credentials are missing required keys, or
    if Cost Management rejects the request (bad credentials, insufficient
    permissions, etc.) or returns a response missing an expected column.
    """
    tenant_id = credentials.get("tenant_id")
    client_id = credentials.get("client_id")
    client_secret = credentials.get("client_secret")
    subscription_id = credentials.get("subscription_id")
    if not tenant_id or not client_id or not client_secret or not subscription_id:
        raise ValidationAppError(
            "Azure credentials must include 'tenant_id', 'client_id', 'client_secret' "
            "and 'subscription_id'",
            code="AZURE_CREDENTIALS_INCOMPLETE",
        )

    credential = ClientSecretCredential(tenant_id, client_id, client_secret)
    client = CostManagementClient(credential)
    scope = f"/subscriptions/{subscription_id}"

    period_end = date.today().replace(day=1)  # exclusive - start of the current, still-open month
    period_start = _subtract_months(period_end, months)

    query = QueryDefinition(
        type="ActualCost",
        timeframe="Custom",
        time_period=QueryTimePeriod(from_property=period_start, to=period_end),
        dataset=QueryDataset(
            granularity="Monthly",
            aggregation={"totalCost": QueryAggregation(name="Cost", function="Sum")},
            grouping=[QueryGrouping(type="Dimension", name="ServiceName")],
        ),
    )

    @_cost_management_retry
    def _query_usage():
        return client.query.usage(scope, query)

    try:
        response = _query_usage()
    except ClientAuthenticationError as exc:
        raise ValidationAppError(
            f"Azure Cost Management rejected the credentials: {exc}",
            code="AZURE_COST_MANAGEMENT_REQUEST_FAILED",
        ) from exc
    except HttpResponseError as exc:
        raise ValidationAppError(
            f"Azure Cost Management rejected the request: {exc.message or exc}",
            code="AZURE_COST_MANAGEMENT_REQUEST_FAILED",
        ) from exc
    except ServiceRequestError as exc:
        raise ValidationAppError(
            f"Could not reach Azure Cost Management: {exc}",
            code="AZURE_COST_MANAGEMENT_REQUEST_FAILED",
        ) from exc

    columns = response.columns
    cost_index = _column_index(columns, "Cost")
    service_index = _column_index(columns, "ServiceName")
    date_index = _column_index(columns, "BillingMonth") or _column_index(columns, "UsageDate")
    currency_index = _column_index(columns, "Currency")

    if cost_index is None or service_index is None or date_index is None:
        raise ValidationAppError(
            "Azure Cost Management response is missing an expected column "
            "(Cost/ServiceName/BillingMonth) - cannot parse billing data",
            code="AZURE_COST_MANAGEMENT_UNEXPECTED_RESPONSE",
        )

    results: list[MonthlyServiceCost] = []
    for row in response.rows:
        amount = float(row[cost_index])
        if amount <= 0:
            continue  # real spend only, matching aws_cost_explorer.py's own skip-zero-cost rule

        raw_date = str(row[date_index])
        # Azure reports the billing month as an 8-digit integer (YYYYMMDD,
        # always the 1st) for Monthly granularity - parse defensively.
        month_start = date(int(raw_date[:4]), int(raw_date[4:6]), 1)
        next_month_start = _subtract_months(month_start, -1)
        month_end = next_month_start - timedelta(days=1)

        results.append(
            {
                "service_name": row[service_index],
                "cost_amount": amount,
                "currency": row[currency_index] if currency_index is not None else "USD",
                "billing_period_start": month_start,
                "billing_period_end": month_end,
            }
        )

    return results
