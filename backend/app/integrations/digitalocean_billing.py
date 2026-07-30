"""Real DigitalOcean billing integration (Phase 28): fetches genuine
monthly spend grouped by product, via `pydo`'s `invoices` API -
DigitalOcean's direct equivalent of AWS Cost Explorer/Azure Cost
Management (app/integrations/aws_cost_explorer.py/azure_cost_management.py),
which this module mirrors closely.

DigitalOcean has no single "cost by service, one call" endpoint the way
AWS/Azure do - `invoices.list()` returns one summary row per finalized
monthly invoice (plus a separate, deliberately-excluded "invoice_preview"
for the current, still-accruing month - the same "closed months only"
rule aws_cost_explorer.py/azure_cost_management.py already follow), and
each invoice's real per-product breakdown is a second call to
`invoices.get_by_uuid()`.
"""
from datetime import date, timedelta
from typing import TypedDict

import pydo
import tenacity
from azure.core.exceptions import HttpResponseError

from app.utils.exceptions import ValidationAppError

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _is_retryable_do_error(exc: BaseException) -> bool:
    return isinstance(exc, HttpResponseError) and exc.status_code in _RETRYABLE_STATUS_CODES


_do_billing_retry = tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable_do_error),
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


def _month_bounds(period: str) -> tuple[date, date]:
    """'YYYY-MM' -> (first day, last day) of that calendar month."""
    year, month = int(period[:4]), int(period[5:7])
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end - timedelta(days=1)


def fetch_monthly_costs_by_service(credentials: dict[str, str], months: int) -> list[MonthlyServiceCost]:
    """Fetches the last `months` complete calendar months of real
    DigitalOcean spend, grouped by product, shaped to match
    CloudCostCreate directly so the caller can hand each entry straight to
    the existing cost-ingestion repository.

    Raises ValidationAppError if credentials are missing required keys, or
    if the DigitalOcean API rejects the request.
    """
    api_token = credentials.get("api_token")
    if not api_token:
        raise ValidationAppError(
            "DigitalOcean credentials must include 'api_token' (a personal access token)",
            code="DIGITALOCEAN_CREDENTIALS_INCOMPLETE",
        )

    client = pydo.Client(token=api_token)

    @_do_billing_retry
    def _list_invoices():
        return client.invoices.list()

    @_do_billing_retry
    def _get_invoice(invoice_uuid: str):
        return client.invoices.get_by_uuid(invoice_uuid=invoice_uuid)

    try:
        invoices_response = _list_invoices()
    except HttpResponseError as exc:
        raise ValidationAppError(
            f"DigitalOcean rejected the billing request: {exc.message or exc}",
            code="DIGITALOCEAN_BILLING_REQUEST_FAILED",
        ) from exc

    invoices = invoices_response.get("invoices", [])
    # invoices.list() is already newest-first in the real API - keep only
    # the last `months` finalized invoices, matching the other providers'
    # closed-months-only rule.
    results: list[MonthlyServiceCost] = []
    for invoice in invoices[:months]:
        period = invoice.get("invoice_period")
        invoice_uuid = invoice.get("invoice_uuid")
        if not period or not invoice_uuid:
            continue
        period_start, period_end = _month_bounds(period)

        try:
            items_response = _get_invoice(invoice_uuid)
        except HttpResponseError as exc:
            raise ValidationAppError(
                f"DigitalOcean rejected the billing request: {exc.message or exc}",
                code="DIGITALOCEAN_BILLING_REQUEST_FAILED",
            ) from exc

        totals_by_product: dict[str, float] = {}
        for item in items_response.get("invoice_items", []):
            amount = float(item.get("amount") or 0.0)
            if amount <= 0:
                continue  # real spend only, matching aws_cost_explorer.py's own skip-zero-cost rule
            product = item.get("product") or item.get("group_description") or item.get("description") or "unknown"
            totals_by_product[product] = totals_by_product.get(product, 0.0) + amount

        for product, amount in totals_by_product.items():
            results.append(
                {
                    "service_name": product,
                    "cost_amount": amount,
                    "currency": "USD",
                    "billing_period_start": period_start,
                    "billing_period_end": period_end,
                }
            )

    return results
