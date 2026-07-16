"""Cloud cost endpoints: ingest billing entries, query history, and forecast
next month's spend for a project."""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.authentication.dependencies import get_current_active_user, require_roles
from app.controllers.cloud_cost_controller import CloudCostController
from app.database.session import get_db
from app.models.user import User
from app.schemas.cloud_cost import CloudCostCreate, CloudCostRead, CostForecastRead
from app.schemas.common import ErrorResponse, PaginatedResponse

router = APIRouter(tags=["Cloud Costs"])


@router.post(
    "/projects/{project_id}/cloud-costs",
    response_model=CloudCostRead,
    status_code=201,
    summary="Ingest a billing entry for a project (operator/admin)",
    dependencies=[Depends(require_roles("operator", "admin"))],
    responses={404: {"model": ErrorResponse, "description": "Project not found"}},
)
def ingest_cloud_cost(
    project_id: int, payload: CloudCostCreate, db: Session = Depends(get_db)
) -> CloudCostRead:
    return CloudCostController(db).ingest(project_id, payload)


@router.get(
    "/projects/{project_id}/cloud-costs",
    response_model=PaginatedResponse[CloudCostRead],
    summary="List billing entries for a project (paginated, filterable by provider/period)",
    responses={404: {"model": ErrorResponse, "description": "Project not found"}},
)
def list_cloud_costs(
    project_id: int,
    provider: str | None = Query(default=None),
    since: date | None = Query(default=None, description="Inclusive lower bound on billing_period_start"),
    until: date | None = Query(default=None, description="Inclusive upper bound on billing_period_end"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> PaginatedResponse[CloudCostRead]:
    return CloudCostController(db).list(project_id, provider, since, until, page, page_size)


@router.get(
    "/projects/{project_id}/cost-forecast",
    response_model=CostForecastRead,
    summary="Predict next month's total cost for a project from its billing history",
    responses={404: {"model": ErrorResponse, "description": "Project not found or no cost history"}},
)
def forecast_cost(
    project_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> CostForecastRead:
    return CloudCostController(db).forecast(project_id)
