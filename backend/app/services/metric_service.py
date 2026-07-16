"""Business logic for ingesting and querying Metric data points."""
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.metric import Metric
from app.repositories.deployment_repository import DeploymentRepository
from app.repositories.metric_repository import MetricRepository
from app.repositories.pod_repository import PodRepository
from app.schemas.metric import MetricCreate
from app.utils.exceptions import NotFoundError, ValidationAppError


class MetricService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = MetricRepository(db)
        self.deployment_repository = DeploymentRepository(db)
        self.pod_repository = PodRepository(db)

    def _get_deployment_or_404(self, deployment_id: int):
        deployment = self.deployment_repository.get_by_id(deployment_id)
        if deployment is None:
            raise NotFoundError(
                f"Deployment {deployment_id} not found", code="DEPLOYMENT_NOT_FOUND"
            )
        return deployment

    def ingest(self, deployment_id: int, payload: MetricCreate) -> Metric:
        self._get_deployment_or_404(deployment_id)

        if payload.pod_id is not None:
            pod = self.pod_repository.get_by_id(payload.pod_id)
            if pod is None:
                raise NotFoundError(f"Pod {payload.pod_id} not found", code="POD_NOT_FOUND")
            if pod.deployment_id != deployment_id:
                raise ValidationAppError(
                    f"Pod {payload.pod_id} does not belong to deployment {deployment_id}",
                    code="POD_DEPLOYMENT_MISMATCH",
                )

        metric = Metric(
            deployment_id=deployment_id,
            pod_id=payload.pod_id,
            metric_type=payload.metric_type,
            value=payload.value,
            unit=payload.unit,
            recorded_at=payload.recorded_at,
        )
        return self.repository.create(metric)

    def list(
        self,
        deployment_id: int,
        metric_type: str | None,
        since: datetime | None,
        until: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Metric], int]:
        self._get_deployment_or_404(deployment_id)
        offset = (page - 1) * page_size
        return self.repository.search(deployment_id, metric_type, since, until, offset, page_size)
