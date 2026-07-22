"""Metric and ResourceUsage ingestion endpoints, nested under a deployment.

These are the write path that will populate real historical data for the
Phase 4 AI models (LSTM forecasting, Isolation Forest, Random Forest) to
train and predict against. Ingestion follows the same RBAC policy as other
writes (operator/admin); a future phase may add API-key based auth for
unattended monitoring agents, but for now the same JWT-based roles apply.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.authentication.dependencies import get_current_active_user, require_roles
from app.config.settings import get_settings
from app.controllers.metric_controller import MetricController
from app.controllers.resource_usage_controller import ResourceUsageController
from app.database.session import get_db
from app.middleware.rate_limiter import limiter
from app.models.user import User
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.metric import MetricCreate, MetricRead
from app.schemas.resource_usage import ResourceUsageCreate, ResourceUsageRead

settings = get_settings()

router = APIRouter(tags=["Metrics"])


@router.post(
    "/deployments/{deployment_id}/metrics",
    response_model=MetricRead,
    status_code=201,
    summary="Ingest a raw metric data point for a deployment (operator/admin)",
    dependencies=[Depends(require_roles("operator", "admin"))],
    responses={
        404: {"model": ErrorResponse, "description": "Deployment or pod not found"},
        422: {"model": ErrorResponse, "description": "Pod does not belong to this deployment"},
    },
)
@limiter.limit(settings.RATE_LIMIT_INGESTION)
def ingest_metric(
    request: Request, deployment_id: int, payload: MetricCreate, db: Session = Depends(get_db)
) -> MetricRead:
    return MetricController(db).ingest(deployment_id, payload)


@router.get(
    "/deployments/{deployment_id}/metrics",
    response_model=PaginatedResponse[MetricRead],
    summary="List metric data points for a deployment (paginated, filterable by type/time range)",
    responses={404: {"model": ErrorResponse, "description": "Deployment not found"}},
)
def list_metrics(
    deployment_id: int,
    metric_type: str | None = Query(default=None),
    since: datetime | None = Query(default=None, description="Inclusive lower bound on recorded_at"),
    until: datetime | None = Query(default=None, description="Inclusive upper bound on recorded_at"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> PaginatedResponse[MetricRead]:
    return MetricController(db).list(deployment_id, metric_type, since, until, page, page_size)


@router.post(
    "/deployments/{deployment_id}/resource-usage",
    response_model=ResourceUsageRead,
    status_code=201,
    summary="Ingest a resource usage snapshot for a deployment (operator/admin)",
    dependencies=[Depends(require_roles("operator", "admin"))],
    responses={404: {"model": ErrorResponse, "description": "Deployment not found"}},
)
@limiter.limit(settings.RATE_LIMIT_INGESTION)
def ingest_resource_usage(
    request: Request, deployment_id: int, payload: ResourceUsageCreate, db: Session = Depends(get_db)
) -> ResourceUsageRead:
    return ResourceUsageController(db).ingest(deployment_id, payload)


@router.get(
    "/deployments/{deployment_id}/resource-usage",
    response_model=PaginatedResponse[ResourceUsageRead],
    summary="List resource usage snapshots for a deployment (paginated, filterable by time range)",
    responses={404: {"model": ErrorResponse, "description": "Deployment not found"}},
)
def list_resource_usage(
    deployment_id: int,
    since: datetime | None = Query(default=None, description="Inclusive lower bound on recorded_at"),
    until: datetime | None = Query(default=None, description="Inclusive upper bound on recorded_at"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> PaginatedResponse[ResourceUsageRead]:
    return ResourceUsageController(db).list(deployment_id, since, until, page, page_size)
