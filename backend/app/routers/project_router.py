"""Project endpoints.

RBAC + ownership policy for all domain-resource endpoints in this platform
(Phase 24): a project - and everything nested under it (microservices,
deployments, pods, metrics, predictions, cloud costs, etc.) - is visible
only to that project's own owner, or a platform `is_superuser` (see
app/utils/ownership.py). Role (`viewer`/`operator`/`admin`) is layered on
top of that and controls WHAT actions an owner may take on their own
data: any authenticated user can read their own resources; `operator`/
`admin` can create and update them; only `admin` can delete them. This
platform was previously modeled as a single shared organization's
internal tool (any authenticated staff member could see all monitored
infrastructure) - Phase 24 converts it into genuine per-tenant isolation.
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
    current_user: User = Depends(get_current_active_user),
) -> PaginatedResponse[ProjectRead]:
    return ProjectController(db).list(name, sort_by, order, page, page_size, current_user)


@router.get(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Get a project by ID (only its own owner, or a platform superuser)",
    responses={
        403: {"model": ErrorResponse, "description": "Project belongs to another user"},
        404: {"model": ErrorResponse, "description": "Project not found"},
    },
)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProjectRead:
    return ProjectController(db).get(project_id, current_user)


@router.put(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Update a project (its own owner, if operator/admin)",
    dependencies=[Depends(require_roles("operator", "admin"))],
    responses={
        403: {"model": ErrorResponse, "description": "Project belongs to another user"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        409: {"model": ErrorResponse, "description": "Project name already exists"},
    },
)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProjectRead:
    return ProjectController(db).update(project_id, payload, current_user)


@router.delete(
    "/{project_id}",
    status_code=204,
    summary="Delete a project (its own owner, if admin)",
    dependencies=[Depends(require_roles("admin"))],
    responses={
        403: {"model": ErrorResponse, "description": "Project belongs to another user"},
        404: {"model": ErrorResponse, "description": "Project not found"},
    },
)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    ProjectController(db).delete(project_id, current_user)


@router.get(
    "/{project_id}/cost-thresholds",
    response_model=ProjectCostThresholdRead,
    summary="Get a project's monthly budget and cost alert threshold overrides",
    responses={
        403: {"model": ErrorResponse, "description": "Project belongs to another user"},
        404: {"model": ErrorResponse, "description": "Project not found"},
    },
)
def get_project_cost_thresholds(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProjectCostThresholdRead:
    return ProjectController(db).get_cost_thresholds(project_id, current_user)


@router.put(
    "/{project_id}/cost-thresholds",
    response_model=ProjectCostThresholdRead,
    summary="Update a project's monthly budget and cost alert threshold overrides (operator/admin)",
    dependencies=[Depends(require_roles("operator", "admin"))],
    responses={
        403: {"model": ErrorResponse, "description": "Project belongs to another user"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        422: {"model": ErrorResponse, "description": "Thresholds are not in strictly ascending order"},
    },
)
def update_project_cost_thresholds(
    project_id: int,
    payload: ProjectCostThresholdUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProjectCostThresholdRead:
    return ProjectController(db).update_cost_thresholds(project_id, payload, current_user)
