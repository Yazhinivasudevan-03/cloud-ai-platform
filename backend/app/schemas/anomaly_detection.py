"""Pydantic schemas for the AnomalyDetection resource (Isolation Forest output)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AnomalyDetectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    deployment_id: int
    metric_type: str
    anomaly_score: float
    is_anomaly: bool
    detected_at: datetime
    details: str | None
    created_at: datetime
