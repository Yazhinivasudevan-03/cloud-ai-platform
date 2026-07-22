"""Deployment endpoints, nested under a microservice."""
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.authentication.dependencies import get_current_active_user, require_roles
from app.config.settings import get_settings
from app.controllers.deployment_controller import DeploymentController
from app.database.session import get_db
from app.middleware.rate_limiter import limiter
from app.models.user import User
from app.schemas.cloud_sync import CloudSyncResult
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.deployment import DeploymentCreate, DeploymentRead, DeploymentUpdate

settings = get_settings()

router = APIRouter(tags=["Deployments"])


@router.post(
    "/microservices/{microservice_id}/deployments",
    response_model=DeploymentRead,
    status_code=201,
    summary="Create a deployment under a microservice (operator/admin)",
    dependencies=[Depends(require_roles("operator", "admin"))],
    responses={
        403: {"model": ErrorResponse, "description": "cloud_provider_account_id belongs to another user"},
        404: {"model": ErrorResponse, "description": "Microservice not found"},
        409: {"model": ErrorResponse, "description": "Deployment already exists in namespace"},
    },
)
def create_deployment(
    microservice_id: int,
    payload: DeploymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DeploymentRead:
    return DeploymentController(db).create(microservice_id, payload, current_user.id)


@router.get(
    "/microservices/{microservice_id}/deployments",
    response_model=PaginatedResponse[DeploymentRead],
    summary="List deployments under a microservice (paginated, filterable, sortable)",
    responses={404: {"model": ErrorResponse, "description": "Microservice not found"}},
)
def list_deployments(
    microservice_id: int,
    status: str | None = Query(default=None),
    namespace: str | None = Query(default=None),
    sort_by: Literal["name", "created_at", "status"] = Query(default="created_at"),
    order: Literal["asc", "desc"] = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> PaginatedResponse[DeploymentRead]:
    return DeploymentController(db).list(
        microservice_id, status, namespace, sort_by, order, page, page_size
    )


@router.get(
    "/deployments/{deployment_id}",
    response_model=DeploymentRead,
    summary="Get a deployment by ID",
    responses={404: {"model": ErrorResponse, "description": "Deployment not found"}},
)
def get_deployment(
    deployment_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> DeploymentRead:
    return DeploymentController(db).get(deployment_id)


@router.put(
    "/deployments/{deployment_id}",
    response_model=DeploymentRead,
    summary="Update a deployment (operator/admin)",
    dependencies=[Depends(require_roles("operator", "admin"))],
    responses={
        403: {"model": ErrorResponse, "description": "cloud_provider_account_id belongs to another user"},
        404: {"model": ErrorResponse, "description": "Deployment not found"},
        409: {"model": ErrorResponse, "description": "Deployment already exists in namespace"},
    },
)
def update_deployment(
    deployment_id: int,
    payload: DeploymentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DeploymentRead:
    return DeploymentController(db).update(deployment_id, payload, current_user.id)


@router.delete(
    "/deployments/{deployment_id}",
    status_code=204,
    summary="Delete a deployment (admin only)",
    dependencies=[Depends(require_roles("admin"))],
    responses={404: {"model": ErrorResponse, "description": "Deployment not found"}},
)
def delete_deployment(deployment_id: int, db: Session = Depends(get_db)) -> None:
    DeploymentController(db).delete(deployment_id)


@router.post(
    "/deployments/{deployment_id}/sync-cloud-metrics",
    response_model=CloudSyncResult,
    summary="Pull real, live resource-usage metrics from this deployment's linked cloud "
    "provider account right now (operator/admin)",
    dependencies=[Depends(require_roles("operator", "admin"))],
    responses={
        404: {"model": ErrorResponse, "description": "Deployment or cloud account not found"},
        422: {
            "model": ErrorResponse,
            "description": "No cloud account/resource linked, or that provider isn't supported yet",
        },
    },
)
@limiter.limit(settings.RATE_LIMIT_CLOUD_SYNC)
def sync_deployment_cloud_metrics(
    request: Request,
    deployment_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> CloudSyncResult:
    return DeploymentController(db).sync_cloud_metrics(deployment_id)
