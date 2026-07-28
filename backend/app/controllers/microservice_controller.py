"""Controller layer for Microservice endpoints."""
import math

from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.common import PaginatedResponse, PaginationMeta
from app.schemas.microservice import MicroserviceCreate, MicroserviceRead, MicroserviceUpdate
from app.services.microservice_service import MicroserviceService


class MicroserviceController:
    def __init__(self, db: Session):
        self.service = MicroserviceService(db)

    def create(
        self, project_id: int, payload: MicroserviceCreate, current_user: User
    ) -> MicroserviceRead:
        microservice = self.service.create(project_id, payload, current_user)
        return MicroserviceRead.model_validate(microservice)

    def get(self, microservice_id: int, current_user: User) -> MicroserviceRead:
        return MicroserviceRead.model_validate(self.service.get(microservice_id, current_user))

    def list(
        self,
        project_id: int,
        name: str | None,
        language: str | None,
        sort_by: str,
        order: str,
        page: int,
        page_size: int,
        current_user: User,
    ) -> PaginatedResponse[MicroserviceRead]:
        items, total = self.service.list(
            project_id, name, language, sort_by, order, page, page_size, current_user
        )
        total_pages = math.ceil(total / page_size) if page_size else 0
        return PaginatedResponse[MicroserviceRead](
            items=[MicroserviceRead.model_validate(i) for i in items],
            meta=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=total_pages
            ),
        )

    def update(
        self, microservice_id: int, payload: MicroserviceUpdate, current_user: User
    ) -> MicroserviceRead:
        return MicroserviceRead.model_validate(
            self.service.update(microservice_id, payload, current_user)
        )

    def delete(self, microservice_id: int, current_user: User) -> None:
        self.service.delete(microservice_id, current_user)
