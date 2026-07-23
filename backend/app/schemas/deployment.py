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
    disk_limit_mb: float | None = Field(
        default=None, ge=0, description="Configured disk limit per pod, in MB (Phase 21)"
    )
    network_limit_kbps: float | None = Field(
        default=None,
        ge=0,
        description="Configured combined (in+out) network bandwidth limit per pod, in kbps (Phase 21)",
    )
    cloud_provider_account_id: int | None = Field(
        default=None,
        description="Cloud provider account to use for syncing real cloud metrics",
    )
    cloud_resource_identifier: str | None = Field(
        default=None,
        max_length=200,
        description="Provider-specific resource ID this deployment maps to, e.g. an EC2 instance ID",
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
    disk_limit_mb: float | None = Field(default=None, ge=0)
    network_limit_kbps: float | None = Field(default=None, ge=0)
    cloud_provider_account_id: int | None = None
    cloud_resource_identifier: str | None = Field(default=None, max_length=200)


class DeploymentRead(DeploymentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    microservice_id: int
    created_at: datetime
    updated_at: datetime
