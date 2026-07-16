"""Unit tests for the pure-Python monthly cost forecaster (no DB needed)."""
from datetime import date

import pytest

from app.optimization.cost_forecaster import aggregate_by_month, forecast_next_month


class _FakeCost:
    def __init__(self, cost_amount: float, billing_period_start: date, currency: str = "USD"):
        self.cost_amount = cost_amount
        self.billing_period_start = billing_period_start
        self.currency = currency


def test_forecast_raises_on_empty_history():
    with pytest.raises(ValueError):
        forecast_next_month([])


def test_forecast_uses_naive_method_for_single_month():
    costs = [_FakeCost(1000.0, date(2026, 6, 1))]
    forecast = forecast_next_month(costs)
    assert forecast.method == "naive_last_period"
    assert forecast.predicted_next_month_cost == 1000.0
    assert forecast.historical_periods_used == 1
    assert forecast.trend_slope_per_month is None


def test_forecast_aggregates_multiple_entries_within_the_same_month():
    costs = [
        _FakeCost(600.0, date(2026, 5, 1)),
        _FakeCost(400.0, date(2026, 5, 15)),
    ]
    monthly = aggregate_by_month(costs)
    assert monthly == [((2026, 5), 1000.0)]


def test_forecast_uses_linear_regression_for_upward_trend():
    costs = [
        _FakeCost(1000.0, date(2026, 4, 1)),
        _FakeCost(1200.0, date(2026, 5, 1)),
        _FakeCost(1400.0, date(2026, 6, 1)),
    ]
    forecast = forecast_next_month(costs)
    assert forecast.method == "linear_regression"
    assert forecast.historical_periods_used == 3
    assert forecast.trend_slope_per_month == 200.0
    assert forecast.predicted_next_month_cost == 1600.0


def test_forecast_never_predicts_negative_cost():
    costs = [
        _FakeCost(300.0, date(2026, 4, 1)),
        _FakeCost(150.0, date(2026, 5, 1)),
        _FakeCost(0.0, date(2026, 6, 1)),
    ]
    forecast = forecast_next_month(costs)
    assert forecast.predicted_next_month_cost >= 0.0
