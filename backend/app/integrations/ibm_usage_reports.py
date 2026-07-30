"""Real IBM Cloud billing integration (Phase 28): fetches genuine monthly
spend grouped by resource, via `ibm-platform-services`' `UsageReportsV4` -
IBM's own official, real "Usage Reports" API and direct equivalent of AWS
Cost Explorer/Azure Cost Management (app/integrations/aws_cost_explorer.py/
azure_cost_management.py), which this module mirrors closely.

IBM Cloud Monitoring (real-time metrics) is deliberately NOT implemented -
see IbmCloudProviderClient.list_monitoring()'s own disclosure: it is a
separate Sysdig-based product requiring a per-instance agent this platform
cannot install, with no official Python SDK for its query API either. Cost
sync has no such dependency - UsageReportsV4 is a plain, already-installed,
account-wide REST API needing only the same IAM API key every other IBM
Cloud call in this platform already uses.
"""
from datetime import date, timedelta

import ibm_platform_services
from ibm_cloud_sdk_core.api_exception import ApiException
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator

from app.utils.exceptions import ValidationAppError


def _resolve_account_id(api_key: str) -> str:
    client = ibm_platform_services.IamIdentityV1(authenticator=IAMAuthenticator(apikey=api_key))
    try:
        result = client.get_api_keys_details(iam_api_key=api_key).get_result()
    except ApiException as exc:
        raise ValidationAppError(
            f"IBM Cloud rejected the credentials while resolving the account ID for billing: {exc.message}",
            code="IBM_CREDENTIALS_REJECTED",
        ) from exc
    account_id = result.get("account_id")
    if not account_id:
        raise ValidationAppError(
            "IBM Cloud did not return an account ID for this API key - cannot fetch billing data",
            code="IBM_ACCOUNT_ID_UNAVAILABLE",
        )
    return account_id


def _month_bounds(period: str) -> tuple[date, date]:
    """'YYYY-MM' -> (first day, last day) of that calendar month."""
    year, month = int(period[:4]), int(period[5:7])
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end - timedelta(days=1)


def _last_n_billing_months(months: int) -> list[str]:
    """The last `months` complete calendar months as 'YYYY-MM' strings,
    oldest first - same "closed months only" rule aws_cost_explorer.py/
    azure_cost_management.py already follow."""
    today = date.today()
    year, month = today.year, today.month
    periods = []
    for _ in range(months):
        month -= 1
        if month == 0:
            month = 12
            year -= 1
        periods.append(f"{year}-{month:02d}")
    return list(reversed(periods))


def fetch_monthly_costs_by_service(credentials: dict[str, str], months: int) -> list:
    """Fetches the last `months` complete calendar months of real IBM
    Cloud spend, grouped by resource, shaped to match CloudCostCreate
    directly so the caller can hand each entry straight to the existing
    cost-ingestion repository.

    Raises ValidationAppError if credentials are missing required keys, or
    if the Usage Reports API rejects the request. A billing month with
    genuinely no usage yet (e.g. a brand-new account's first month) is
    skipped rather than treated as a hard failure.
    """
    api_key = credentials.get("api_key")
    if not api_key:
        raise ValidationAppError(
            "IBM Cloud credentials must include 'api_key' (an IAM API key)",
            code="IBM_CREDENTIALS_INCOMPLETE",
        )

    account_id = _resolve_account_id(api_key)
    client = ibm_platform_services.UsageReportsV4(authenticator=IAMAuthenticator(apikey=api_key))

    results = []
    for period in _last_n_billing_months(months):
        try:
            response = client.get_account_usage(account_id, period, names=True)
        except ApiException as exc:
            if exc.status_code == 404:
                continue  # no usage report exists yet for this month - not a failure
            raise ValidationAppError(
                f"IBM Cloud Usage Reports rejected the request ({exc.status_code}): {exc.message}",
                code="IBM_USAGE_REPORTS_REQUEST_FAILED",
            ) from exc

        report = response.get_result()
        period_start, period_end = _month_bounds(period)
        currency = report.get("currency_code", "USD")
        for resource in report.get("resources", []):
            amount = float(resource.get("billable_cost") or 0.0)
            if amount <= 0:
                continue  # real spend only, matching aws_cost_explorer.py's own skip-zero-cost rule
            results.append(
                {
                    "service_name": resource.get("resource_name") or resource.get("resource_id", "unknown"),
                    "cost_amount": amount,
                    "currency": currency,
                    "billing_period_start": period_start,
                    "billing_period_end": period_end,
                }
            )

    return results
