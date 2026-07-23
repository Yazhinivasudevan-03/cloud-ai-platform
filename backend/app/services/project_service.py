"""Business logic for the Project resource."""
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models.project import Project
from app.models.user import User
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import (
    ProjectCostThresholdRead,
    ProjectCostThresholdUpdate,
    ProjectCreate,
    ProjectUpdate,
)
from app.utils.exceptions import ConflictError, NotFoundError, ValidationAppError

_COST_TIERS = ("cost_warning_threshold", "cost_critical_threshold", "cost_saturated_threshold")


class ProjectService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = ProjectRepository(db)
        self.settings = get_settings()

    def create(self, payload: ProjectCreate, owner: User) -> Project:
        if self.repository.get_by_name(payload.name) is not None:
            raise ConflictError(
                f"A project named '{payload.name}' already exists", code="PROJECT_EXISTS"
            )
        project = Project(name=payload.name, description=payload.description, owner_id=owner.id)
        return self.repository.create(project)

    def get(self, project_id: int) -> Project:
        project = self.repository.get_by_id(project_id)
        if project is None:
            raise NotFoundError(f"Project {project_id} not found", code="PROJECT_NOT_FOUND")
        return project

    def list(
        self, name_contains: str | None, sort_by: str, order: str, page: int, page_size: int
    ) -> tuple[list[Project], int]:
        offset = (page - 1) * page_size
        return self.repository.search(name_contains, sort_by, order, offset, page_size)

    def update(self, project_id: int, payload: ProjectUpdate) -> Project:
        project = self.get(project_id)
        if payload.name is not None and payload.name != project.name:
            if self.repository.get_by_name(payload.name) is not None:
                raise ConflictError(
                    f"A project named '{payload.name}' already exists", code="PROJECT_EXISTS"
                )
            project.name = payload.name
        if payload.description is not None:
            project.description = payload.description
        self.db.commit()
        self.db.refresh(project)
        return project

    def delete(self, project_id: int) -> None:
        project = self.get(project_id)
        self.repository.delete(project)

    def get_cost_thresholds(self, project_id: int) -> ProjectCostThresholdRead:
        project = self.get(project_id)
        return self._to_cost_threshold_read(project)

    def update_cost_thresholds(
        self, project_id: int, payload: ProjectCostThresholdUpdate
    ) -> ProjectCostThresholdRead:
        project = self.get(project_id)
        data = payload.model_dump(exclude_unset=True)

        for field in ("monthly_budget", *_COST_TIERS):
            if field in data:
                setattr(project, field, data[field])

        self._validate_cost_tier_ordering(project)

        self.db.commit()
        self.db.refresh(project)
        return self._to_cost_threshold_read(project)

    def _validate_cost_tier_ordering(self, project: Project) -> None:
        warning, critical, saturated = (self._effective_cost(project, f) for f in _COST_TIERS)
        if not (warning < critical < saturated):
            raise ValidationAppError(
                f"cost_warning_threshold={warning}, cost_critical_threshold={critical}, "
                f"cost_saturated_threshold={saturated} - each tier must be strictly "
                "greater than the one before it",
                code="INVALID_THRESHOLD_ORDERING",
            )

    def _effective_cost(self, project: Project, field: str) -> float:
        value = getattr(project, field)
        if value is not None:
            return value
        return getattr(self.settings, f"ALERT_{field.upper()}")

    def _to_cost_threshold_read(self, project: Project) -> ProjectCostThresholdRead:
        return ProjectCostThresholdRead(
            project_id=project.id,
            monthly_budget=project.monthly_budget,
            cost_warning_threshold=project.cost_warning_threshold,
            cost_critical_threshold=project.cost_critical_threshold,
            cost_saturated_threshold=project.cost_saturated_threshold,
            effective_cost_warning_threshold=self._effective_cost(project, "cost_warning_threshold"),
            effective_cost_critical_threshold=self._effective_cost(project, "cost_critical_threshold"),
            effective_cost_saturated_threshold=self._effective_cost(project, "cost_saturated_threshold"),
        )
