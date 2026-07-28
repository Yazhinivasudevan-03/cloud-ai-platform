"""Controller layer for Deployment endpoints."""
import math

from sqlalchemy.orm import Session

from app.models.user import User
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
        self, microservice_id: int, payload: DeploymentCreate, current_user: User
    ) -> DeploymentRead:
        deployment = self.service.create(microservice_id, payload, current_user)
        return DeploymentRead.model_validate(deployment)

    def get(self, deployment_id: int, current_user: User) -> DeploymentRead:
        return DeploymentRead.model_validate(self.service.get(deployment_id, current_user))

    def list(
        self,
        microservice_id: int,
        status: str | None,
        namespace: str | None,
        sort_by: str,
        order: str,
        page: int,
        page_size: int,
        current_user: User,
        cloud_provider_account_id: int | None = None,
    ) -> PaginatedResponse[DeploymentRead]:
        items, total = self.service.list(
            microservice_id,
            status,
            namespace,
            sort_by,
            order,
            page,
            page_size,
            current_user,
            cloud_provider_account_id,
        )
        total_pages = math.ceil(total / page_size) if page_size else 0
        return PaginatedResponse[DeploymentRead](
            items=[DeploymentRead.model_validate(i) for i in items],
            meta=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=total_pages
            ),
        )

    def update(
        self, deployment_id: int, payload: DeploymentUpdate, current_user: User
    ) -> DeploymentRead:
        return DeploymentRead.model_validate(
            self.service.update(deployment_id, payload, current_user)
        )

    def delete(self, deployment_id: int, current_user: User) -> None:
        self.service.delete(deployment_id, current_user)

    def sync_cloud_metrics(self, deployment_id: int, current_user: User) -> CloudSyncResult:
        # Ownership-checked via the same DeploymentService.get() every
        # other single-deployment endpoint uses - CloudSyncService itself
        # stays user-agnostic since the scheduled job (sync_all) also
        # calls it, system-wide, with no request-scoped user at all.
        self.service.get(deployment_id, current_user)
        return self.cloud_sync_service.sync_deployment(deployment_id)
