"""Business logic for the Deployment resource."""
from sqlalchemy.orm import Session

from app.models.deployment import Deployment
from app.repositories.deployment_repository import DeploymentRepository
from app.repositories.microservice_repository import MicroserviceRepository
from app.schemas.deployment import DeploymentCreate, DeploymentUpdate
from app.utils.exceptions import ConflictError, NotFoundError


class DeploymentService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = DeploymentRepository(db)
        self.microservice_repository = MicroserviceRepository(db)

    def _get_microservice_or_404(self, microservice_id: int):
        microservice = self.microservice_repository.get_by_id(microservice_id)
        if microservice is None:
            raise NotFoundError(
                f"Microservice {microservice_id} not found", code="MICROSERVICE_NOT_FOUND"
            )
        return microservice

    def create(self, microservice_id: int, payload: DeploymentCreate) -> Deployment:
        self._get_microservice_or_404(microservice_id)
        if (
            self.repository.get_by_microservice_identity(
                microservice_id, payload.name, payload.namespace
            )
            is not None
        ):
            raise ConflictError(
                f"A deployment named '{payload.name}' already exists in namespace "
                f"'{payload.namespace}' for this microservice",
                code="DEPLOYMENT_EXISTS",
            )
        deployment = Deployment(
            microservice_id=microservice_id,
            name=payload.name,
            namespace=payload.namespace,
            image=payload.image,
            version=payload.version,
            replicas=payload.replicas,
            status=payload.status.value,
            memory_limit_mb=payload.memory_limit_mb,
        )
        return self.repository.create(deployment)

    def get(self, deployment_id: int) -> Deployment:
        deployment = self.repository.get_by_id(deployment_id)
        if deployment is None:
            raise NotFoundError(
                f"Deployment {deployment_id} not found", code="DEPLOYMENT_NOT_FOUND"
            )
        return deployment

    def list(
        self,
        microservice_id: int,
        status: str | None,
        namespace: str | None,
        sort_by: str,
        order: str,
        page: int,
        page_size: int,
    ) -> tuple[list[Deployment], int]:
        self._get_microservice_or_404(microservice_id)
        offset = (page - 1) * page_size
        return self.repository.search(
            microservice_id, status, namespace, sort_by, order, offset, page_size
        )

    def update(self, deployment_id: int, payload: DeploymentUpdate) -> Deployment:
        deployment = self.get(deployment_id)
        new_name = payload.name if payload.name is not None else deployment.name
        new_namespace = (
            payload.namespace if payload.namespace is not None else deployment.namespace
        )
        if (new_name, new_namespace) != (deployment.name, deployment.namespace):
            existing = self.repository.get_by_microservice_identity(
                deployment.microservice_id, new_name, new_namespace
            )
            if existing is not None and existing.id != deployment.id:
                raise ConflictError(
                    f"A deployment named '{new_name}' already exists in namespace "
                    f"'{new_namespace}' for this microservice",
                    code="DEPLOYMENT_EXISTS",
                )
        deployment.name = new_name
        deployment.namespace = new_namespace
        if payload.image is not None:
            deployment.image = payload.image
        if payload.version is not None:
            deployment.version = payload.version
        if payload.replicas is not None:
            deployment.replicas = payload.replicas
        if payload.status is not None:
            deployment.status = payload.status.value
        if payload.memory_limit_mb is not None:
            deployment.memory_limit_mb = payload.memory_limit_mb
        self.db.commit()
        self.db.refresh(deployment)
        return deployment

    def delete(self, deployment_id: int) -> None:
        deployment = self.get(deployment_id)
        self.repository.delete(deployment)
