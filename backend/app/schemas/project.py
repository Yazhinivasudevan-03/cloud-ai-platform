"""Pydantic schemas for the Project resource."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectBase(BaseModel):
    name: str = Field(..., min_length=3, max_length=150)
    description: str | None = Field(default=None, max_length=2000)


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=150)
    description: str | None = Field(default=None, max_length=2000)


class ProjectRead(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime


class ProjectCostThresholdUpdate(BaseModel):
    """Cost alerting (Phase 21) - null fields fall back to the
    platform-wide ALERT_COST_*_THRESHOLD defaults. monthly_budget itself
    has no default - cost alerting is skipped entirely for a project
    without one configured."""

    monthly_budget: float | None = Field(default=None, ge=0)
    cost_warning_threshold: float | None = Field(default=None, ge=0, le=100)
    cost_critical_threshold: float | None = Field(default=None, ge=0, le=100)
    cost_saturated_threshold: float | None = Field(default=None, ge=0, le=100)


class ProjectCostThresholdRead(BaseModel):
    project_id: int
    monthly_budget: float | None
    cost_warning_threshold: float | None
    cost_critical_threshold: float | None
    cost_saturated_threshold: float | None
    effective_cost_warning_threshold: float
    effective_cost_critical_threshold: float
    effective_cost_saturated_threshold: float
