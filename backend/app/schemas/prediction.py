"""Pydantic schemas for the Prediction resource (LSTM forecast output)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PredictionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    deployment_id: int
    model_type: str
    metric_type: str
    predicted_value: float
    confidence_score: float
    target_timestamp: datetime
    generated_at: datetime
    created_at: datetime
