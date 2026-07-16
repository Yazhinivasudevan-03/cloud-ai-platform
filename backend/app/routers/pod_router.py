"""Pod endpoints, nested under a deployment."""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.authentication.dependencies import get_current_active_user, require_roles
from app.controllers.pod_controller import PodController
from app.database.session import get_db
from app.models.user import User
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.pod import PodCreate, PodRead, PodUpdate

router = APIRouter(tags=["Pods"])


@router.post(
    "/deployments/{deployment_id}/pods",
    response_model=PodRead,
    status_code=201,
    summary="Register a pod under a deployment (operator/admin)",
    dependencies=[Depends(require_roles("operator", "admin"))],
    responses={
        404: {"model": ErrorResponse, "description": "Deployment not found"},
        409: {"model": ErrorResponse, "description": "Pod already exists for this deployment"},
    },
)
def create_pod(
    deployment_id: int, payload: PodCreate, db: Session = Depends(get_db)
) -> PodRead:
    return PodController(db).create(deployment_id, payload)


@router.get(
    "/deployments/{deployment_id}/pods",
    response_model=PaginatedResponse[PodRead],
    summary="List pods under a deployment (paginated, filterable, sortable)",
    responses={404: {"model": ErrorResponse, "description": "Deployment not found"}},
)
def list_pods(
    deployment_id: int,
    status: str | None = Query(default=None),
    sort_by: Literal["pod_name", "created_at"] = Query(default="created_at"),
    order: Literal["asc", "desc"] = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> PaginatedResponse[PodRead]:
    return PodController(db).list(deployment_id, status, sort_by, order, page, page_size)


@router.get(
    "/pods/{pod_id}",
    response_model=PodRead,
    summary="Get a pod by ID",
    responses={404: {"model": ErrorResponse, "description": "Pod not found"}},
)
def get_pod(
    pod_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> PodRead:
    return PodController(db).get(pod_id)


@router.put(
    "/pods/{pod_id}",
    response_model=PodRead,
    summary="Update a pod (operator/admin)",
    dependencies=[Depends(require_roles("operator", "admin"))],
    responses={404: {"model": ErrorResponse, "description": "Pod not found"}},
)
def update_pod(pod_id: int, payload: PodUpdate, db: Session = Depends(get_db)) -> PodRead:
    return PodController(db).update(pod_id, payload)


@router.delete(
    "/pods/{pod_id}",
    status_code=204,
    summary="Delete a pod (admin only)",
    dependencies=[Depends(require_roles("admin"))],
    responses={404: {"model": ErrorResponse, "description": "Pod not found"}},
)
def delete_pod(pod_id: int, db: Session = Depends(get_db)) -> None:
    PodController(db).delete(pod_id)
