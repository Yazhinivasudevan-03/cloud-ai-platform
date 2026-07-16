"""Business logic for ingesting and querying ResourceUsage snapshots."""
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.resource_usage import ResourceUsage
from app.repositories.deployment_repository import DeploymentRepository
from app.repositories.resource_usage_repository import ResourceUsageRepository
from app.schemas.resource_usage import ResourceUsageCreate
from app.utils.exceptions import NotFoundError


class ResourceUsageService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = ResourceUsageRepository(db)
        self.deployment_repository = DeploymentRepository(db)

    def _get_deployment_or_404(self, deployment_id: int):
        deployment = self.deployment_repository.get_by_id(deployment_id)
        if deployment is None:
            raise NotFoundError(
                f"Deployment {deployment_id} not found", code="DEPLOYMENT_NOT_FOUND"
            )
        return deployment

    def ingest(self, deployment_id: int, payload: ResourceUsageCreate) -> ResourceUsage:
        self._get_deployment_or_404(deployment_id)
        usage = ResourceUsage(
            deployment_id=deployment_id,
            cpu_usage_percent=payload.cpu_usage_percent,
            memory_usage_mb=payload.memory_usage_mb,
            disk_usage_mb=payload.disk_usage_mb,
            network_in_kbps=payload.network_in_kbps,
            network_out_kbps=payload.network_out_kbps,
            recorded_at=payload.recorded_at,
        )
        return self.repository.create(usage)

    def list(
        self,
        deployment_id: int,
        since: datetime | None,
        until: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[ResourceUsage], int]:
        self._get_deployment_or_404(deployment_id)
        offset = (page - 1) * page_size
        return self.repository.search(deployment_id, since, until, offset, page_size)
