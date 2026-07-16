"""Pydantic schemas for the CloudCost resource and its derived cost forecast."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CloudCostCreate(BaseModel):
    provider: str = Field(
        ..., min_length=2, max_length=30, description="e.g. aws, azure, gcp, on_prem"
    )
    service_name: str = Field(..., min_length=1, max_length=100)
    cost_amount: float = Field(..., ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    billing_period_start: date
    billing_period_end: date

    @model_validator(mode="after")
    def check_period_order(self) -> "CloudCostCreate":
        if self.billing_period_end < self.billing_period_start:
            raise ValueError("billing_period_end must not be before billing_period_start")
        return self


class CloudCostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    provider: str
    service_name: str
    cost_amount: float
    currency: str
    billing_period_start: date
    billing_period_end: date
    created_at: datetime


class CostForecastRead(BaseModel):
    predicted_next_month_cost: float
    currency: str
    method: str
    historical_periods_used: int
    trend_slope_per_month: float | None
