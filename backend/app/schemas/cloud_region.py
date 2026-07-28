"""Pydantic schemas for dynamic multi-cloud region discovery (Phase 25)."""
from datetime import datetime

from pydantic import BaseModel, Field


class CloudRegionRead(BaseModel):
    id: str
    display_name: str


class CloudAccountRegionsRead(BaseModel):
    selected_region: str
    regions: list[CloudRegionRead]
    last_region_sync: datetime | None
    connection_status: str


class SelectRegionRequest(BaseModel):
    # The literal "all" is a valid value (see CloudProviderAccount.region's
    # docstring) - it isn't restricted to available_regions, since it means
    # "aggregate across every region" rather than naming one.
    selected_region: str = Field(..., min_length=1, max_length=50)


class RegionSyncSummary(BaseModel):
    accounts_attempted: int
    accounts_synced: int
    accounts_failed: int
