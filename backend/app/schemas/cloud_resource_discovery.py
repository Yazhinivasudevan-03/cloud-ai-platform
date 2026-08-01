"""Pydantic schemas for Phase 29's automatic AWS resource discovery /
persistence pipeline - distinct from app/schemas/cloud_resource.py (Phase
25C's on-demand, never-persisted browse endpoint), which is left untouched."""
from datetime import datetime

from pydantic import BaseModel


class ResourceDiscoverySummary(BaseModel):
    accounts_attempted: int
    accounts_discovered: int
    accounts_failed: int


class Ec2MetricRead(BaseModel):
    model_config = {"from_attributes": True}

    cpu_usage_percent: float
    memory_usage_mb: float | None
    network_in_kbps: float
    network_out_kbps: float
    disk_read_bytes: float
    disk_write_bytes: float
    status_check_failed: int | None
    recorded_at: datetime


class DiscoveredResourceRead(BaseModel):
    id: int
    resource_type: str
    external_id: str
    name: str
    region: str
    availability_zone: str | None
    status: str
    instance_type: str | None
    public_ip: str | None
    private_ip: str | None
    is_active: bool
    first_seen_at: datetime
    last_seen_at: datetime
    latest_metric: Ec2MetricRead | None = None


class DiscoveredResourceListRead(BaseModel):
    items: list[DiscoveredResourceRead]


class CloudAccountDiscoverySummary(BaseModel):
    total_instances: int
    running_instances: int
    stopped_instances: int
    resource_counts_by_type: dict[str, int]
    last_discovery_at: datetime | None
    last_discovery_error: str | None
