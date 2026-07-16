"""Pydantic schemas for the Pod resource."""
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PodStatus(StrEnum):
    RUNNING = "running"
    PENDING = "pending"
    FAILED = "failed"
    SUCCEEDED = "succeeded"
    UNKNOWN = "unknown"


class PodBase(BaseModel):
    pod_name: str = Field(..., min_length=1, max_length=150)
    node_name: str | None = Field(default=None, max_length=150)
    ip_address: str | None = Field(default=None, max_length=45)
    status: PodStatus = PodStatus.UNKNOWN
    restart_count: int = Field(default=0, ge=0)


class PodCreate(PodBase):
    pass


class PodUpdate(BaseModel):
    node_name: str | None = Field(default=None, max_length=150)
    ip_address: str | None = Field(default=None, max_length=45)
    status: PodStatus | None = None
    restart_count: int | None = Field(default=None, ge=0)


class PodRead(PodBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    deployment_id: int
    created_at: datetime
    updated_at: datetime
