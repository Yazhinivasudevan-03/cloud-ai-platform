"""Pydantic schemas for the cloud resource inventory (Phase 25C) and
provisioning (Phase 25D) endpoints - mirrors
app/integrations/cloud_provider_client.py's CloudResourceSummary TypedDict
exactly, since every provider adapter already returns that shape."""
from datetime import datetime

from pydantic import BaseModel, Field

RESOURCE_CATEGORIES = ("compute", "clusters", "databases", "storage", "networking")

# Only these 3 categories are provisionable (Phase 25D) - clusters/databases
# are read-only inventory only in this pass, never fabricated as
# deployable when they genuinely aren't yet.
PROVISIONABLE_RESOURCE_TYPES = ("compute", "storage", "networking")


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


class DeployResourceRequest(BaseModel):
    resource_type: str = Field(..., description="compute | storage | networking")
    region: str
    spec: dict = Field(default_factory=dict, description="Provider- and resource-type-specific deploy parameters")


class DestroyResourceRequest(BaseModel):
    region: str
    confirm: str = Field(..., min_length=1, description="Must exactly match the resource's own id/name")
