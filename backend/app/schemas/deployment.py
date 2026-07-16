"""Pydantic schemas for the Deployment resource."""
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DeploymentStatus(StrEnum):
    RUNNING = "running"
    PENDING = "pending"
    FAILED = "failed"
    UNKNOWN = "unknown"


class DeploymentBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    namespace: str = Field(default="default", min_length=1, max_length=100)
    image: str | None = Field(default=None, max_length=255)
    version: str | None = Field(default=None, max_length=50)
    replicas: int = Field(default=1, ge=0)
    status: DeploymentStatus = DeploymentStatus.UNKNOWN
    memory_limit_mb: float | None = Field(
        default=None, ge=0, description="Configured memory limit per pod, in MB"
    )


class DeploymentCreate(DeploymentBase):
    pass


class DeploymentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    namespace: str | None = Field(default=None, min_length=1, max_length=100)
    image: str | None = Field(default=None, max_length=255)
    version: str | None = Field(default=None, max_length=50)
    replicas: int | None = Field(default=None, ge=0)
    status: DeploymentStatus | None = None
    memory_limit_mb: float | None = Field(default=None, ge=0)


class DeploymentRead(DeploymentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    microservice_id: int
    created_at: datetime
    updated_at: datetime
