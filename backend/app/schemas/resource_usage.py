"""Pydantic schemas for the ResourceUsage resource (aggregated snapshots)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ResourceUsageCreate(BaseModel):
    cpu_usage_percent: float = Field(..., ge=0)
    memory_usage_mb: float = Field(..., ge=0)
    disk_usage_mb: float = Field(..., ge=0)
    network_in_kbps: float = Field(..., ge=0)
    network_out_kbps: float = Field(..., ge=0)
    recorded_at: datetime


class ResourceUsageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    deployment_id: int
    cpu_usage_percent: float
    memory_usage_mb: float
    disk_usage_mb: float
    network_in_kbps: float
    network_out_kbps: float
    recorded_at: datetime
    created_at: datetime
