"""Controller layer for Pod endpoints."""
import math

from sqlalchemy.orm import Session

from app.schemas.common import PaginatedResponse, PaginationMeta
from app.schemas.pod import PodCreate, PodRead, PodUpdate
from app.services.pod_service import PodService


class PodController:
    def __init__(self, db: Session):
        self.service = PodService(db)

    def create(self, deployment_id: int, payload: PodCreate) -> PodRead:
        pod = self.service.create(deployment_id, payload)
        return PodRead.model_validate(pod)

    def get(self, pod_id: int) -> PodRead:
        return PodRead.model_validate(self.service.get(pod_id))

    def list(
        self,
        deployment_id: int,
        status: str | None,
        sort_by: str,
        order: str,
        page: int,
        page_size: int,
    ) -> PaginatedResponse[PodRead]:
        items, total = self.service.list(deployment_id, status, sort_by, order, page, page_size)
        total_pages = math.ceil(total / page_size) if page_size else 0
        return PaginatedResponse[PodRead](
            items=[PodRead.model_validate(i) for i in items],
            meta=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=total_pages
            ),
        )

    def update(self, pod_id: int, payload: PodUpdate) -> PodRead:
        return PodRead.model_validate(self.service.update(pod_id, payload))

    def delete(self, pod_id: int) -> None:
        self.service.delete(pod_id)
