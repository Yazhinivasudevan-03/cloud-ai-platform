"""Pydantic schemas for the OptimizationRecommendation resource."""
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class OptimizationRecommendationStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    DISMISSED = "dismissed"


class OptimizationRecommendationUpdate(BaseModel):
    status: OptimizationRecommendationStatus = Field(
        ..., description="Transition target: applied or dismissed"
    )


class OptimizationRecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    deployment_id: int
    recommendation_type: str
    description: str
    estimated_savings: float | None
    status: str
    created_at: datetime
    updated_at: datetime


class OptimizationEvaluationSummary(BaseModel):
    deployments_evaluated: int
    recommendations_created: int
    recommendations_dismissed: int
