"""Controller layer for Deployment endpoints."""
import math

from sqlalchemy.orm import Session

from app.schemas.cloud_sync import CloudSyncResult
from app.schemas.common import PaginatedResponse, PaginationMeta
from app.schemas.deployment import DeploymentCreate, DeploymentRead, DeploymentUpdate
from app.services.cloud_sync_service import CloudSyncService
from app.services.deployment_service import DeploymentService


class DeploymentController:
    def __init__(self, db: Session):
        self.service = DeploymentService(db)
        self.cloud_sync_service = CloudSyncService(db)

    def create(
        self, microservice_id: int, payload: DeploymentCreate, current_user_id: int
    ) -> DeploymentRead:
        deployment = self.service.create(microservice_id, payload, current_user_id)
        return DeploymentRead.model_validate(deployment)

    def get(self, deployment_id: int) -> DeploymentRead:
        return DeploymentRead.model_validate(self.service.get(deployment_id))

    def list(
        self,
        microservice_id: int,
        status: str | None,
        namespace: str | None,
        sort_by: str,
        order: str,
        page: int,
        page_size: int,
    ) -> PaginatedResponse[DeploymentRead]:
        items, total = self.service.list(
            microservice_id, status, namespace, sort_by, order, page, page_size
        )
        total_pages = math.ceil(total / page_size) if page_size else 0
        return PaginatedResponse[DeploymentRead](
            items=[DeploymentRead.model_validate(i) for i in items],
            meta=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=total_pages
            ),
        )

    def update(
        self, deployment_id: int, payload: DeploymentUpdate, current_user_id: int
    ) -> DeploymentRead:
        return DeploymentRead.model_validate(
            self.service.update(deployment_id, payload, current_user_id)
        )

    def delete(self, deployment_id: int) -> None:
        self.service.delete(deployment_id)

    def sync_cloud_metrics(self, deployment_id: int) -> CloudSyncResult:
        return self.cloud_sync_service.sync_deployment(deployment_id)
