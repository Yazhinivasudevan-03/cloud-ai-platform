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

    # Phase 22 - multi-timezone support. Populated only when the metric's
    # deployment is linked to a configured cloud account timezone entry;
    # null otherwise (existing deployments are unaffected/UTC-only).
    utc_timestamp: datetime | None = None
    local_timestamp: str | None = Field(
        default=None, description="e.g. '2026-08-15 18:35 BST'"
    )
    deployment_timezone: str | None = Field(default=None, description="IANA identifier, e.g. 'Europe/London'")
    region: str | None = None
    provider: str | None = None
