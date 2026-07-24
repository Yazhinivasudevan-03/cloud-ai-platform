"""Pydantic schemas for the CloudAccountTimezone resource (Phase 22) -
multi-timezone support for cloud accounts. `timezone` must be a real IANA
identifier (validated server-side via app/utils/timezones.py); `utc_offset`
and `current_local_time` are always computed fresh at read time, never
stored, so they're correct across Daylight Saving Time transitions.
"""
from datetime import datetime

from pydantic import BaseModel, Field


class CloudAccountTimezoneCreate(BaseModel):
    region: str = Field(..., min_length=1, max_length=50, description="e.g. eu-west-2, ap-south-1")
    availability_zone: str | None = Field(default=None, max_length=50, description="e.g. eu-west-2a")
    label: str = Field(..., min_length=1, max_length=150, description="e.g. 'London Production'")
    timezone: str = Field(
        ..., min_length=1, max_length=64, description="IANA identifier, e.g. 'Europe/London'"
    )


class CloudAccountTimezoneUpdate(BaseModel):
    region: str | None = Field(default=None, min_length=1, max_length=50)
    availability_zone: str | None = Field(default=None, max_length=50)
    label: str | None = Field(default=None, min_length=1, max_length=150)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)


class CloudAccountTimezoneRead(BaseModel):
    id: int
    cloud_provider_account_id: int
    provider: str
    region: str
    availability_zone: str | None
    label: str
    timezone: str
    utc_offset: str
    current_local_time: str
    created_at: datetime
    updated_at: datetime


class TimezoneValidationResult(BaseModel):
    timezone: str
    valid: bool
    utc_offset: str | None = None
    current_local_time: str | None = None
    error: str | None = None
