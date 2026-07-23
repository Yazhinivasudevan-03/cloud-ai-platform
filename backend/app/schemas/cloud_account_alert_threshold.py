"""Pydantic schemas for per-cloud-account CPU/memory/disk/network alert
threshold overrides (Phase 20-21). Any field left null means "use the
platform-wide default for this tier" - see app/config/settings.py's
ALERT_CPU_*/ALERT_MEMORY_*/ALERT_DISK_*/ALERT_NETWORK_* settings and
AlertEvaluationService's resolution order. Cost thresholds live on
Project instead - see app/schemas/project.py.
"""
from pydantic import BaseModel, Field


class CloudAccountAlertThresholdUpdate(BaseModel):
    cpu_warning_threshold: float | None = Field(default=None, ge=0, le=100)
    cpu_critical_threshold: float | None = Field(default=None, ge=0, le=100)
    cpu_saturated_threshold: float | None = Field(default=None, ge=0, le=100)
    memory_warning_threshold: float | None = Field(default=None, ge=0, le=100)
    memory_critical_threshold: float | None = Field(default=None, ge=0, le=100)
    memory_saturated_threshold: float | None = Field(default=None, ge=0, le=100)
    disk_warning_threshold: float | None = Field(default=None, ge=0, le=100)
    disk_critical_threshold: float | None = Field(default=None, ge=0, le=100)
    disk_saturated_threshold: float | None = Field(default=None, ge=0, le=100)
    network_warning_threshold: float | None = Field(default=None, ge=0, le=100)
    network_critical_threshold: float | None = Field(default=None, ge=0, le=100)
    network_saturated_threshold: float | None = Field(default=None, ge=0, le=100)


class CloudAccountAlertThresholdRead(BaseModel):
    cloud_provider_account_id: int
    cpu_warning_threshold: float | None
    cpu_critical_threshold: float | None
    cpu_saturated_threshold: float | None
    memory_warning_threshold: float | None
    memory_critical_threshold: float | None
    memory_saturated_threshold: float | None
    disk_warning_threshold: float | None
    disk_critical_threshold: float | None
    disk_saturated_threshold: float | None
    network_warning_threshold: float | None
    network_critical_threshold: float | None
    network_saturated_threshold: float | None
    # The values actually in effect right now - the override above, or the
    # platform-wide Settings default when unset - so the UI can show "60%
    # (default)" vs "70% (custom)" without duplicating the fallback logic.
    effective_cpu_warning_threshold: float
    effective_cpu_critical_threshold: float
    effective_cpu_saturated_threshold: float
    effective_memory_warning_threshold: float
    effective_memory_critical_threshold: float
    effective_memory_saturated_threshold: float
    effective_disk_warning_threshold: float
    effective_disk_critical_threshold: float
    effective_disk_saturated_threshold: float
    effective_network_warning_threshold: float
    effective_network_critical_threshold: float
    effective_network_saturated_threshold: float
