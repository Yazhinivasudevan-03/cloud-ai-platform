"""Business logic for the Microservice resource."""
from sqlalchemy.orm import Session

from app.models.microservice import Microservice
from app.models.user import User
from app.repositories.microservice_repository import MicroserviceRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.microservice import MicroserviceCreate, MicroserviceUpdate
from app.utils.exceptions import ConflictError, NotFoundError
from app.utils.ownership import raise_if_cannot_access_project


class MicroserviceService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = MicroserviceRepository(db)
        self.project_repository = ProjectRepository(db)

    def _get_project_or_404(self, project_id: int, current_user: User):
        project = self.project_repository.get_by_id(project_id)
        if project is None:
            raise NotFoundError(f"Project {project_id} not found", code="PROJECT_NOT_FOUND")
        raise_if_cannot_access_project(project, current_user)
        return project

    def create(self, project_id: int, payload: MicroserviceCreate, current_user: User) -> Microservice:
        self._get_project_or_404(project_id, current_user)
        if self.repository.get_by_project_and_name(project_id, payload.name) is not None:
            raise ConflictError(
                f"A microservice named '{payload.name}' already exists in this project",
                code="MICROSERVICE_EXISTS",
            )
        microservice = Microservice(
            project_id=project_id,
            name=payload.name,
            description=payload.description,
            repository_url=payload.repository_url,
            language=payload.language,
        )
        return self.repository.create(microservice)

    def get(self, microservice_id: int, current_user: User) -> Microservice:
        microservice = self.repository.get_by_id(microservice_id)
        if microservice is None:
            raise NotFoundError(
                f"Microservice {microservice_id} not found", code="MICROSERVICE_NOT_FOUND"
            )
        raise_if_cannot_access_project(microservice.project, current_user)
        return microservice

    def list(
        self,
        project_id: int,
        name_contains: str | None,
        language: str | None,
        sort_by: str,
        order: str,
        page: int,
        page_size: int,
        current_user: User,
    ) -> tuple[list[Microservice], int]:
        self._get_project_or_404(project_id, current_user)
        offset = (page - 1) * page_size
        return self.repository.search(
            project_id, name_contains, language, sort_by, order, offset, page_size
        )

    def update(self, microservice_id: int, payload: MicroserviceUpdate, current_user: User) -> Microservice:
        microservice = self.get(microservice_id, current_user)
        if payload.name is not None and payload.name != microservice.name:
            if (
                self.repository.get_by_project_and_name(microservice.project_id, payload.name)
                is not None
            ):
                raise ConflictError(
                    f"A microservice named '{payload.name}' already exists in this project",
                    code="MICROSERVICE_EXISTS",
                )
            microservice.name = payload.name
        if payload.description is not None:
            microservice.description = payload.description
        if payload.repository_url is not None:
            microservice.repository_url = payload.repository_url
        if payload.language is not None:
            microservice.language = payload.language
        self.db.commit()
        self.db.refresh(microservice)
        return microservice

    def delete(self, microservice_id: int, current_user: User) -> None:
        microservice = self.get(microservice_id, current_user)
        self.repository.delete(microservice)
