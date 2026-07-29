"""Pydantic schemas for the read-only cloud resource inventory (Phase 25C) -
mirrors app/integrations/cloud_provider_client.py's CloudResourceSummary
TypedDict exactly, since every provider adapter already returns that shape."""
from datetime import datetime

from pydantic import BaseModel

RESOURCE_CATEGORIES = ("compute", "clusters", "databases", "storage", "networking")


class CloudResourceRead(BaseModel):
    id: str
    name: str
    type: str
    region: str
    status: str
    created_at: datetime | None = None


class CloudResourceListRead(BaseModel):
    category: str
    region: str
    items: list[CloudResourceRead]
