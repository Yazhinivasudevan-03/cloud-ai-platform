"""Business logic for the Pod resource."""
from sqlalchemy.orm import Session

from app.models.pod import Pod
from app.repositories.deployment_repository import DeploymentRepository
from app.repositories.pod_repository import PodRepository
from app.schemas.pod import PodCreate, PodUpdate
from app.utils.exceptions import ConflictError, NotFoundError


class PodService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = PodRepository(db)
        self.deployment_repository = DeploymentRepository(db)

    def _get_deployment_or_404(self, deployment_id: int):
        deployment = self.deployment_repository.get_by_id(deployment_id)
        if deployment is None:
            raise NotFoundError(
                f"Deployment {deployment_id} not found", code="DEPLOYMENT_NOT_FOUND"
            )
        return deployment

    def create(self, deployment_id: int, payload: PodCreate) -> Pod:
        self._get_deployment_or_404(deployment_id)
        if self.repository.get_by_deployment_and_name(deployment_id, payload.pod_name) is not None:
            raise ConflictError(
                f"A pod named '{payload.pod_name}' already exists for this deployment",
                code="POD_EXISTS",
            )
        pod = Pod(
            deployment_id=deployment_id,
            pod_name=payload.pod_name,
            node_name=payload.node_name,
            ip_address=payload.ip_address,
            status=payload.status.value,
            restart_count=payload.restart_count,
        )
        return self.repository.create(pod)

    def get(self, pod_id: int) -> Pod:
        pod = self.repository.get_by_id(pod_id)
        if pod is None:
            raise NotFoundError(f"Pod {pod_id} not found", code="POD_NOT_FOUND")
        return pod

    def list(
        self,
        deployment_id: int,
        status: str | None,
        sort_by: str,
        order: str,
        page: int,
        page_size: int,
    ) -> tuple[list[Pod], int]:
        self._get_deployment_or_404(deployment_id)
        offset = (page - 1) * page_size
        return self.repository.search(deployment_id, status, sort_by, order, offset, page_size)

    def update(self, pod_id: int, payload: PodUpdate) -> Pod:
        pod = self.get(pod_id)
        if payload.node_name is not None:
            pod.node_name = payload.node_name
        if payload.ip_address is not None:
            pod.ip_address = payload.ip_address
        if payload.status is not None:
            pod.status = payload.status.value
        if payload.restart_count is not None:
            pod.restart_count = payload.restart_count
        self.db.commit()
        self.db.refresh(pod)
        return pod

    def delete(self, pod_id: int) -> None:
        pod = self.get(pod_id)
        self.repository.delete(pod)
