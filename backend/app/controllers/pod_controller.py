"""Controller layer for Pod endpoints."""
import math

from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.common import PaginatedResponse, PaginationMeta
from app.schemas.pod import PodCreate, PodRead, PodUpdate
from app.services.pod_service import PodService


class PodController:
    def __init__(self, db: Session):
        self.service = PodService(db)

    def create(self, deployment_id: int, payload: PodCreate, current_user: User) -> PodRead:
        pod = self.service.create(deployment_id, payload, current_user)
        return PodRead.model_validate(pod)

    def get(self, pod_id: int, current_user: User) -> PodRead:
        return PodRead.model_validate(self.service.get(pod_id, current_user))

    def list(
        self,
        deployment_id: int,
        status: str | None,
        sort_by: str,
        order: str,
        page: int,
        page_size: int,
        current_user: User,
    ) -> PaginatedResponse[PodRead]:
        items, total = self.service.list(
            deployment_id, status, sort_by, order, page, page_size, current_user
        )
        total_pages = math.ceil(total / page_size) if page_size else 0
        return PaginatedResponse[PodRead](
            items=[PodRead.model_validate(i) for i in items],
            meta=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=total_pages
            ),
        )

    def update(self, pod_id: int, payload: PodUpdate, current_user: User) -> PodRead:
        return PodRead.model_validate(self.service.update(pod_id, payload, current_user))

    def delete(self, pod_id: int, current_user: User) -> None:
        self.service.delete(pod_id, current_user)
