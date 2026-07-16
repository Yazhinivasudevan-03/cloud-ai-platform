"""Business logic for the Project resource."""
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.user import User
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.utils.exceptions import ConflictError, NotFoundError


class ProjectService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = ProjectRepository(db)

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
