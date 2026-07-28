"""Controller layer for Project endpoints."""
import math

from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.common import PaginatedResponse, PaginationMeta
from app.schemas.project import (
    ProjectCostThresholdRead,
    ProjectCostThresholdUpdate,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
)
from app.services.project_service import ProjectService


class ProjectController:
    def __init__(self, db: Session):
        self.service = ProjectService(db)

    def create(self, payload: ProjectCreate, owner: User) -> ProjectRead:
        project = self.service.create(payload, owner)
        return ProjectRead.model_validate(project)

    def get(self, project_id: int, current_user: User) -> ProjectRead:
        return ProjectRead.model_validate(self.service.get(project_id, current_user))

    def list(
        self,
        name: str | None,
        sort_by: str,
        order: str,
        page: int,
        page_size: int,
        current_user: User,
    ) -> PaginatedResponse[ProjectRead]:
        items, total = self.service.list(name, sort_by, order, page, page_size, current_user)
        total_pages = math.ceil(total / page_size) if page_size else 0
        return PaginatedResponse[ProjectRead](
            items=[ProjectRead.model_validate(i) for i in items],
            meta=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=total_pages
            ),
        )

    def update(self, project_id: int, payload: ProjectUpdate, current_user: User) -> ProjectRead:
        return ProjectRead.model_validate(self.service.update(project_id, payload, current_user))

    def delete(self, project_id: int, current_user: User) -> None:
        self.service.delete(project_id, current_user)

    def get_cost_thresholds(self, project_id: int, current_user: User) -> ProjectCostThresholdRead:
        return self.service.get_cost_thresholds(project_id, current_user)

    def update_cost_thresholds(
        self, project_id: int, payload: ProjectCostThresholdUpdate, current_user: User
    ) -> ProjectCostThresholdRead:
        return self.service.update_cost_thresholds(project_id, payload, current_user)
