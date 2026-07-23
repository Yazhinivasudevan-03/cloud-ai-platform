"""Project endpoints.

RBAC policy for all domain-resource endpoints in this platform: any
authenticated user (default role `viewer`) can read; `operator`/`admin` can
create and update; only `admin` can delete. Resource ownership (`owner_id`)
is recorded for audit purposes but is not an access-control boundary, since
this platform models an internal cloud-ops monitoring tool (all authorized
staff can see all monitored infrastructure) rather than multi-tenant SaaS.
"""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.authentication.dependencies import get_current_active_user, require_roles
from app.controllers.project_controller import ProjectController
from app.database.session import get_db
from app.models.user import User
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.project import (
    ProjectCostThresholdRead,
    ProjectCostThresholdUpdate,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
)

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post(
    "",
    response_model=ProjectRead,
    status_code=201,
    summary="Create a project (operator/admin)",
    dependencies=[Depends(require_roles("operator", "admin"))],
    responses={409: {"model": ErrorResponse, "description": "Project name already exists"}},
)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProjectRead:
    return ProjectController(db).create(payload, current_user)


@router.get(
    "",
    response_model=PaginatedResponse[ProjectRead],
    summary="List projects (paginated, filterable, sortable)",
)
def list_projects(
    name: str | None = Query(default=None, description="Case-insensitive substring filter"),
    sort_by: Literal["name", "created_at"] = Query(default="created_at"),
    order: Literal["asc", "desc"] = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> PaginatedResponse[ProjectRead]:
    return ProjectController(db).list(name, sort_by, order, page, page_size)


@router.get(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Get a project by ID",
    responses={404: {"model": ErrorResponse, "description": "Project not found"}},
)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> ProjectRead:
    return ProjectController(db).get(project_id)


@router.put(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Update a project (operator/admin)",
    dependencies=[Depends(require_roles("operator", "admin"))],
    responses={
        404: {"model": ErrorResponse, "description": "Project not found"},
        409: {"model": ErrorResponse, "description": "Project name already exists"},
    },
)
def update_project(
    project_id: int, payload: ProjectUpdate, db: Session = Depends(get_db)
) -> ProjectRead:
    return ProjectController(db).update(project_id, payload)


@router.delete(
    "/{project_id}",
    status_code=204,
    summary="Delete a project (admin only)",
    dependencies=[Depends(require_roles("admin"))],
    responses={404: {"model": ErrorResponse, "description": "Project not found"}},
)
def delete_project(project_id: int, db: Session = Depends(get_db)) -> None:
    ProjectController(db).delete(project_id)


@router.get(
    "/{project_id}/cost-thresholds",
    response_model=ProjectCostThresholdRead,
    summary="Get a project's monthly budget and cost alert threshold overrides",
    responses={404: {"model": ErrorResponse, "description": "Project not found"}},
)
def get_project_cost_thresholds(
    project_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> ProjectCostThresholdRead:
    return ProjectController(db).get_cost_thresholds(project_id)


@router.put(
    "/{project_id}/cost-thresholds",
    response_model=ProjectCostThresholdRead,
    summary="Update a project's monthly budget and cost alert threshold overrides (operator/admin)",
    dependencies=[Depends(require_roles("operator", "admin"))],
    responses={
        404: {"model": ErrorResponse, "description": "Project not found"},
        422: {"model": ErrorResponse, "description": "Thresholds are not in strictly ascending order"},
    },
)
def update_project_cost_thresholds(
    project_id: int, payload: ProjectCostThresholdUpdate, db: Session = Depends(get_db)
) -> ProjectCostThresholdRead:
    return ProjectController(db).update_cost_thresholds(project_id, payload)
