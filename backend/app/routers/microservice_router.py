"""Microservice endpoints, nested under a project."""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.authentication.dependencies import get_current_active_user, require_roles
from app.controllers.microservice_controller import MicroserviceController
from app.database.session import get_db
from app.models.user import User
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.microservice import MicroserviceCreate, MicroserviceRead, MicroserviceUpdate

router = APIRouter(tags=["Microservices"])


@router.post(
    "/projects/{project_id}/microservices",
    response_model=MicroserviceRead,
    status_code=201,
    summary="Create a microservice under a project (operator/admin)",
    dependencies=[Depends(require_roles("operator", "admin"))],
    responses={
        404: {"model": ErrorResponse, "description": "Project not found"},
        409: {"model": ErrorResponse, "description": "Microservice name already exists in project"},
    },
)
def create_microservice(
    project_id: int, payload: MicroserviceCreate, db: Session = Depends(get_db)
) -> MicroserviceRead:
    return MicroserviceController(db).create(project_id, payload)


@router.get(
    "/projects/{project_id}/microservices",
    response_model=PaginatedResponse[MicroserviceRead],
    summary="List microservices under a project (paginated, filterable, sortable)",
    responses={404: {"model": ErrorResponse, "description": "Project not found"}},
)
def list_microservices(
    project_id: int,
    name: str | None = Query(default=None, description="Case-insensitive substring filter"),
    language: str | None = Query(default=None),
    sort_by: Literal["name", "created_at"] = Query(default="created_at"),
    order: Literal["asc", "desc"] = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> PaginatedResponse[MicroserviceRead]:
    return MicroserviceController(db).list(
        project_id, name, language, sort_by, order, page, page_size
    )


@router.get(
    "/microservices/{microservice_id}",
    response_model=MicroserviceRead,
    summary="Get a microservice by ID",
    responses={404: {"model": ErrorResponse, "description": "Microservice not found"}},
)
def get_microservice(
    microservice_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> MicroserviceRead:
    return MicroserviceController(db).get(microservice_id)


@router.put(
    "/microservices/{microservice_id}",
    response_model=MicroserviceRead,
    summary="Update a microservice (operator/admin)",
    dependencies=[Depends(require_roles("operator", "admin"))],
    responses={
        404: {"model": ErrorResponse, "description": "Microservice not found"},
        409: {"model": ErrorResponse, "description": "Microservice name already exists in project"},
    },
)
def update_microservice(
    microservice_id: int, payload: MicroserviceUpdate, db: Session = Depends(get_db)
) -> MicroserviceRead:
    return MicroserviceController(db).update(microservice_id, payload)


@router.delete(
    "/microservices/{microservice_id}",
    status_code=204,
    summary="Delete a microservice (admin only)",
    dependencies=[Depends(require_roles("admin"))],
    responses={404: {"model": ErrorResponse, "description": "Microservice not found"}},
)
def delete_microservice(microservice_id: int, db: Session = Depends(get_db)) -> None:
    MicroserviceController(db).delete(microservice_id)
