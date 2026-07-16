"""Controller layer for AI-model-output read endpoints."""
import math
from datetime import datetime

from sqlalchemy.orm import Session

from app.schemas.anomaly_detection import AnomalyDetectionRead
from app.schemas.common import PaginatedResponse, PaginationMeta
from app.schemas.failure_prediction import FailurePredictionRead
from app.schemas.prediction import PredictionRead
from app.services.prediction_service import PredictionService


class PredictionController:
    def __init__(self, db: Session):
        self.service = PredictionService(db)

    def list_predictions(
        self,
        deployment_id: int,
        metric_type: str | None,
        model_type: str | None,
        since: datetime | None,
        until: datetime | None,
        page: int,
        page_size: int,
    ) -> PaginatedResponse[PredictionRead]:
        items, total = self.service.list_predictions(
            deployment_id, metric_type, model_type, since, until, page, page_size
        )
        total_pages = math.ceil(total / page_size) if page_size else 0
        return PaginatedResponse[PredictionRead](
            items=[PredictionRead.model_validate(i) for i in items],
            meta=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=total_pages
            ),
        )

    def list_anomaly_detections(
        self,
        deployment_id: int,
        is_anomaly: bool | None,
        since: datetime | None,
        until: datetime | None,
        page: int,
        page_size: int,
    ) -> PaginatedResponse[AnomalyDetectionRead]:
        items, total = self.service.list_anomaly_detections(
            deployment_id, is_anomaly, since, until, page, page_size
        )
        total_pages = math.ceil(total / page_size) if page_size else 0
        return PaginatedResponse[AnomalyDetectionRead](
            items=[AnomalyDetectionRead.model_validate(i) for i in items],
            meta=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=total_pages
            ),
        )

    def list_failure_predictions(
        self,
        deployment_id: int,
        failure_type: str | None,
        since: datetime | None,
        until: datetime | None,
        page: int,
        page_size: int,
    ) -> PaginatedResponse[FailurePredictionRead]:
        items, total = self.service.list_failure_predictions(
            deployment_id, failure_type, since, until, page, page_size
        )
        total_pages = math.ceil(total / page_size) if page_size else 0
        return PaginatedResponse[FailurePredictionRead](
            items=[FailurePredictionRead.model_validate(i) for i in items],
            meta=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=total_pages
            ),
        )
