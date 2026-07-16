"""Pydantic schemas for the Metric resource (raw time-series data points)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MetricCreate(BaseModel):
    metric_type: str = Field(
        ..., min_length=2, max_length=50, description="e.g. cpu_usage, memory_usage, latency"
    )
    value: float
    unit: str = Field(..., min_length=1, max_length=20, description="e.g. percent, MB, ms")
    recorded_at: datetime
    pod_id: int | None = Field(
        default=None, description="Optional pod this metric was collected from"
    )


class MetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    deployment_id: int | None
    pod_id: int | None
    metric_type: str
    value: float
    unit: str
    recorded_at: datetime
    created_at: datetime
