"""Read-only query logic for AI model output: predictions, anomaly detections,
and failure predictions. All three are written by the independent ml-models
batch pipeline (see ml-models/), never through this API - these services only
validate the parent deployment exists and delegate filtering/pagination to
their repositories.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.anomaly_detection import AnomalyDetection
from app.models.failure_prediction import FailurePrediction
from app.models.prediction import Prediction
from app.repositories.anomaly_detection_repository import AnomalyDetectionRepository
from app.repositories.deployment_repository import DeploymentRepository
from app.repositories.failure_prediction_repository import FailurePredictionRepository
from app.repositories.prediction_repository import PredictionRepository
from app.utils.exceptions import NotFoundError


class PredictionService:
    def __init__(self, db: Session):
        self.prediction_repository = PredictionRepository(db)
        self.anomaly_detection_repository = AnomalyDetectionRepository(db)
        self.failure_prediction_repository = FailurePredictionRepository(db)
        self.deployment_repository = DeploymentRepository(db)

    def _get_deployment_or_404(self, deployment_id: int):
        deployment = self.deployment_repository.get_by_id(deployment_id)
        if deployment is None:
            raise NotFoundError(
                f"Deployment {deployment_id} not found", code="DEPLOYMENT_NOT_FOUND"
            )
        return deployment

    def list_predictions(
        self,
        deployment_id: int,
        metric_type: str | None,
        model_type: str | None,
        since: datetime | None,
        until: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Prediction], int]:
        self._get_deployment_or_404(deployment_id)
        offset = (page - 1) * page_size
        return self.prediction_repository.search(
            deployment_id, metric_type, model_type, since, until, offset, page_size
        )

    def list_anomaly_detections(
        self,
        deployment_id: int,
        is_anomaly: bool | None,
        since: datetime | None,
        until: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AnomalyDetection], int]:
        self._get_deployment_or_404(deployment_id)
        offset = (page - 1) * page_size
        return self.anomaly_detection_repository.search(
            deployment_id, is_anomaly, since, until, offset, page_size
        )

    def list_failure_predictions(
        self,
        deployment_id: int,
        failure_type: str | None,
        since: datetime | None,
        until: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[FailurePrediction], int]:
        self._get_deployment_or_404(deployment_id)
        offset = (page - 1) * page_size
        return self.failure_prediction_repository.search(
            deployment_id, failure_type, since, until, offset, page_size
        )
