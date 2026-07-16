"""Pydantic schemas for the Microservice resource."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MicroserviceBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    repository_url: str | None = Field(default=None, max_length=255)
    language: str | None = Field(default=None, max_length=50)


class MicroserviceCreate(MicroserviceBase):
    pass


class MicroserviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    repository_url: str | None = Field(default=None, max_length=255)
    language: str | None = Field(default=None, max_length=50)


class MicroserviceRead(MicroserviceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    created_at: datetime
    updated_at: datetime
