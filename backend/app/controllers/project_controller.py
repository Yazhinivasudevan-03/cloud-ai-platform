"""Controller layer for Project endpoints."""
import math

from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.common import PaginatedResponse, PaginationMeta
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services.project_service import ProjectService


class ProjectController:
    def __init__(self, db: Session):
        self.service = ProjectService(db)

    def create(self, payload: ProjectCreate, owner: User) -> ProjectRead:
        project = self.service.create(payload, owner)
        return ProjectRead.model_validate(project)

    def get(self, project_id: int) -> ProjectRead:
        return ProjectRead.model_validate(self.service.get(project_id))

    def list(
        self, name: str | None, sort_by: str, order: str, page: int, page_size: int
    ) -> PaginatedResponse[ProjectRead]:
        items, total = self.service.list(name, sort_by, order, page, page_size)
        total_pages = math.ceil(total / page_size) if page_size else 0
        return PaginatedResponse[ProjectRead](
            items=[ProjectRead.model_validate(i) for i in items],
            meta=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=total_pages
            ),
        )

    def update(self, project_id: int, payload: ProjectUpdate) -> ProjectRead:
        return ProjectRead.model_validate(self.service.update(project_id, payload))

    def delete(self, project_id: int) -> None:
        self.service.delete(project_id)
