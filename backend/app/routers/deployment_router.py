"""Deployment endpoints, nested under a microservice."""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.authentication.dependencies import get_current_active_user, require_roles
from app.controllers.deployment_controller import DeploymentController
from app.database.session import get_db
from app.models.user import User
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.deployment import DeploymentCreate, DeploymentRead, DeploymentUpdate

router = APIRouter(tags=["Deployments"])


@router.post(
    "/microservices/{microservice_id}/deployments",
    response_model=DeploymentRead,
    status_code=201,
    summary="Create a deployment under a microservice (operator/admin)",
    dependencies=[Depends(require_roles("operator", "admin"))],
    responses={
        404: {"model": ErrorResponse, "description": "Microservice not found"},
        409: {"model": ErrorResponse, "description": "Deployment already exists in namespace"},
    },
)
def create_deployment(
    microservice_id: int, payload: DeploymentCreate, db: Session = Depends(get_db)
) -> DeploymentRead:
    return DeploymentController(db).create(microservice_id, payload)


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
        404: {"model": ErrorResponse, "description": "Deployment not found"},
        409: {"model": ErrorResponse, "description": "Deployment already exists in namespace"},
    },
)
def update_deployment(
    deployment_id: int, payload: DeploymentUpdate, db: Session = Depends(get_db)
) -> DeploymentRead:
    return DeploymentController(db).update(deployment_id, payload)


@router.delete(
    "/deployments/{deployment_id}",
    status_code=204,
    summary="Delete a deployment (admin only)",
    dependencies=[Depends(require_roles("admin"))],
    responses={404: {"model": ErrorResponse, "description": "Deployment not found"}},
)
def delete_deployment(deployment_id: int, db: Session = Depends(get_db)) -> None:
    DeploymentController(db).delete(deployment_id)
