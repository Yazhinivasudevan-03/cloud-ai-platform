"""Pydantic schemas for dynamic multi-cloud region discovery (Phase 25)."""
from datetime import datetime

from pydantic import BaseModel, Field


class CloudRegionRead(BaseModel):
    id: str
    display_name: str
    # Phase 30: best-effort enrichment from app/integrations/region_metadata.py
    # - None for a region code that table doesn't cover yet (never
    # fabricated). Optional/default-None so a pre-Phase-30 stored
    # available_regions blob (missing these keys entirely) still parses.
    country: str | None = None
    timezone: str | None = None


class CloudAccountRegionsRead(BaseModel):
    selected_region: str
    regions: list[CloudRegionRead]
    last_region_sync: datetime | None
    connection_status: str
    # Phase 30 (requirement 6 - automatic region->timezone mapping):
    # the currently selected region's real IANA timezone, resolved
    # server-side from this same account's available_regions - None only
    # when selected_region is "all" (no single timezone applies) or the
    # region_metadata table doesn't cover this region code yet.
    selected_region_timezone: str | None = None


class SelectRegionRequest(BaseModel):
    # The literal "all" is a valid value (see CloudProviderAccount.region's
    # docstring) - it isn't restricted to available_regions, since it means
    # "aggregate across every region" rather than naming one.
    selected_region: str = Field(..., min_length=1, max_length=50)


class RegionSyncSummary(BaseModel):
    accounts_attempted: int
    accounts_synced: int
    accounts_failed: int
