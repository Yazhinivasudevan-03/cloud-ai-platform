"""Pydantic schemas for the Alert resource."""
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AlertStatus(StrEnum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AlertUpdate(BaseModel):
    status: AlertStatus = Field(..., description="Transition target: acknowledged or resolved")


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    deployment_id: int | None
    alert_type: str
    severity: str
    threshold_percent: float | None
    message: str
    status: str
    triggered_at: datetime
    resolved_at: datetime | None
    created_at: datetime


class AlertEvaluationSummary(BaseModel):
    """Response for POST /alerts/evaluate - what the rule engine just did."""

    deployments_evaluated: int
    alerts_created: int
    alerts_resolved: int
    notifications_sent: int
