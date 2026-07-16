"""Read endpoints for AI model output (predictions, anomaly detections,
failure predictions). All are written by the independent ml-models batch
pipeline (see ml-models/) directly against MySQL - there is no POST here by
design; this API's job is to serve that data, not to run inference.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.authentication.dependencies import get_current_active_user
from app.controllers.prediction_controller import PredictionController
from app.database.session import get_db
from app.models.user import User
from app.schemas.anomaly_detection import AnomalyDetectionRead
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.failure_prediction import FailurePredictionRead
from app.schemas.prediction import PredictionRead

router = APIRouter(tags=["AI Predictions"])


@router.get(
    "/deployments/{deployment_id}/predictions",
    response_model=PaginatedResponse[PredictionRead],
    summary="List LSTM workload forecasts for a deployment",
    responses={404: {"model": ErrorResponse, "description": "Deployment not found"}},
)
def list_predictions(
    deployment_id: int,
    metric_type: str | None = Query(default=None),
    model_type: str | None = Query(default=None),
    since: datetime | None = Query(default=None, description="Inclusive lower bound on target_timestamp"),
    until: datetime | None = Query(default=None, description="Inclusive upper bound on target_timestamp"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> PaginatedResponse[PredictionRead]:
    return PredictionController(db).list_predictions(
        deployment_id, metric_type, model_type, since, until, page, page_size
    )


@router.get(
    "/deployments/{deployment_id}/anomaly-detections",
    response_model=PaginatedResponse[AnomalyDetectionRead],
    summary="List Isolation Forest anomaly detections for a deployment",
    responses={404: {"model": ErrorResponse, "description": "Deployment not found"}},
)
def list_anomaly_detections(
    deployment_id: int,
    is_anomaly: bool | None = Query(default=None),
    since: datetime | None = Query(default=None, description="Inclusive lower bound on detected_at"),
    until: datetime | None = Query(default=None, description="Inclusive upper bound on detected_at"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> PaginatedResponse[AnomalyDetectionRead]:
    return PredictionController(db).list_anomaly_detections(
        deployment_id, is_anomaly, since, until, page, page_size
    )


@router.get(
    "/deployments/{deployment_id}/failure-predictions",
    response_model=PaginatedResponse[FailurePredictionRead],
    summary="List Random Forest failure predictions for a deployment",
    responses={404: {"model": ErrorResponse, "description": "Deployment not found"}},
)
def list_failure_predictions(
    deployment_id: int,
    failure_type: str | None = Query(default=None),
    since: datetime | None = Query(default=None, description="Inclusive lower bound on predicted_at"),
    until: datetime | None = Query(default=None, description="Inclusive upper bound on predicted_at"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> PaginatedResponse[FailurePredictionRead]:
    return PredictionController(db).list_failure_predictions(
        deployment_id, failure_type, since, until, page, page_size
    )
