"""Pydantic schemas for the on-demand / scheduled cloud-metrics-sync action."""
from datetime import datetime

from pydantic import BaseModel


class CloudSyncResult(BaseModel):
    deployment_id: int
    cloud_provider_account_id: int
    provider: str
    resource_identifier: str
    synced_at: datetime
    resource_usage_id: int


class CloudSyncAllSummary(BaseModel):
    deployments_attempted: int
    deployments_synced: int
    deployments_failed: int
