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
    project_id: int | None
    alert_type: str
    severity: str
    threshold_percent: float | None
    message: str
    status: str
    triggered_at: datetime
    resolved_at: datetime | None
    created_at: datetime

    # Phase 22 - multi-timezone support. Populated only when the alert's
    # deployment is linked to a configured cloud account timezone entry
    # (project-scoped cost alerts and deployments without one configured
    # keep these null - core alerting is unchanged).
    alert_time_utc: datetime | None = None
    alert_time_local: str | None = Field(
        default=None, description="e.g. '2026-08-15 18:35 BST'"
    )
    deployment_timezone: str | None = Field(default=None, description="IANA identifier, e.g. 'Europe/London'")
    region: str | None = None
    provider: str | None = None


class AlertEvaluationSummary(BaseModel):
    """Response for POST /alerts/evaluate - what the rule engine just did."""

    deployments_evaluated: int
    projects_evaluated: int
    alerts_created: int
    alerts_resolved: int
    notifications_sent: int
