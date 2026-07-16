"""Lightweight monthly cost forecasting over `cloud_costs` history.

A straight-line trend fit needs nothing heavier than ordinary least squares
over a handful of monthly totals - not enough to justify pulling numpy/pandas
into the backend (or routing this through the ml-models pipeline, which is
reserved for the genuinely model-based Phase 4 work). Pure Python is both
sufficient and easier to audit for something this simple.
"""
from dataclasses import dataclass
from datetime import date

from app.models.cloud_cost import CloudCost


@dataclass(frozen=True)
class CostForecast:
    predicted_next_month_cost: float
    currency: str
    method: str  # "linear_regression" | "naive_last_period"
    historical_periods_used: int
    trend_slope_per_month: float | None


def _month_key(d: date) -> tuple[int, int]:
    return (d.year, d.month)


def aggregate_by_month(costs: list[CloudCost]) -> list[tuple[tuple[int, int], float]]:
    """Sum `cost_amount` per calendar month (keyed by `billing_period_start`),
    sorted chronologically."""
    totals: dict[tuple[int, int], float] = {}
    for cost in costs:
        key = _month_key(cost.billing_period_start)
        totals[key] = totals.get(key, 0.0) + float(cost.cost_amount)
    return sorted(totals.items())


def forecast_next_month(costs: list[CloudCost]) -> CostForecast:
    if not costs:
        raise ValueError("No cloud cost history available to forecast from")

    monthly = aggregate_by_month(costs)
    currency = costs[0].currency

    if len(monthly) == 1:
        return CostForecast(
            predicted_next_month_cost=round(monthly[0][1], 2),
            currency=currency,
            method="naive_last_period",
            historical_periods_used=1,
            trend_slope_per_month=None,
        )

    xs = list(range(len(monthly)))
    ys = [amount for _, amount in monthly]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denominator = sum((x - mean_x) ** 2 for x in xs)
    slope = numerator / denominator if denominator else 0.0
    intercept = mean_y - slope * mean_x

    predicted = max(0.0, intercept + slope * n)  # cost can't be negative

    return CostForecast(
        predicted_next_month_cost=round(predicted, 2),
        currency=currency,
        method="linear_regression",
        historical_periods_used=n,
        trend_slope_per_month=round(slope, 2),
    )
