"""Pydantic schemas for the FailurePrediction resource (Random Forest output)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FailurePredictionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    deployment_id: int
    pod_id: int | None
    failure_type: str
    probability: float
    predicted_at: datetime
    created_at: datetime
