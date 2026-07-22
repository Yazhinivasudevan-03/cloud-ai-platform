"""Cloud cost endpoints: ingest billing entries, query history, and forecast
next month's spend for a project."""
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.authentication.dependencies import get_current_active_user, require_roles
from app.config.settings import get_settings
from app.controllers.cloud_cost_controller import CloudCostController
from app.database.session import get_db
from app.middleware.rate_limiter import limiter
from app.models.user import User
from app.schemas.cloud_cost import CloudCostCreate, CloudCostRead, CostForecastRead
from app.schemas.common import ErrorResponse, PaginatedResponse

settings = get_settings()

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


@router.post(
    "/projects/{project_id}/cloud-costs/sync",
    response_model=list[CloudCostRead],
    status_code=201,
    summary="Pull real AWS Cost Explorer billing data for a linked cloud provider "
    "account into this project (operator/admin)",
    dependencies=[Depends(require_roles("operator", "admin"))],
    responses={
        403: {"model": ErrorResponse, "description": "cloud_provider_account_id belongs to another user"},
        404: {"model": ErrorResponse, "description": "Project or cloud account not found"},
        422: {"model": ErrorResponse, "description": "That provider isn't supported yet"},
    },
)
@limiter.limit(settings.RATE_LIMIT_CLOUD_SYNC)
def sync_project_cloud_costs(
    request: Request,
    project_id: int,
    cloud_provider_account_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[CloudCostRead]:
    return CloudCostController(db).sync_from_aws(project_id, cloud_provider_account_id, current_user.id)


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
