"""Business logic for cloud cost ingestion, querying, and monthly forecasting."""
from datetime import date

from sqlalchemy.orm import Session

from app.models.cloud_cost import CloudCost
from app.optimization.cost_forecaster import CostForecast, forecast_next_month
from app.repositories.cloud_cost_repository import CloudCostRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.cloud_cost import CloudCostCreate
from app.utils.exceptions import NotFoundError


class CloudCostService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = CloudCostRepository(db)
        self.project_repository = ProjectRepository(db)

    def _get_project_or_404(self, project_id: int):
        project = self.project_repository.get_by_id(project_id)
        if project is None:
            raise NotFoundError(f"Project {project_id} not found", code="PROJECT_NOT_FOUND")
        return project

    def ingest(self, project_id: int, payload: CloudCostCreate) -> CloudCost:
        self._get_project_or_404(project_id)
        cost = CloudCost(
            project_id=project_id,
            provider=payload.provider,
            service_name=payload.service_name,
            cost_amount=payload.cost_amount,
            currency=payload.currency,
            billing_period_start=payload.billing_period_start,
            billing_period_end=payload.billing_period_end,
        )
        return self.repository.create(cost)

    def list(
        self,
        project_id: int,
        provider: str | None,
        since: date | None,
        until: date | None,
        page: int,
        page_size: int,
    ) -> tuple[list[CloudCost], int]:
        self._get_project_or_404(project_id)
        offset = (page - 1) * page_size
        return self.repository.search(project_id, provider, since, until, offset, page_size)

    def forecast(self, project_id: int) -> CostForecast:
        self._get_project_or_404(project_id)
        costs = self.repository.list_all_for_project(project_id)
        if not costs:
            raise NotFoundError(
                f"No cloud cost history for project {project_id} to forecast from",
                code="NO_COST_HISTORY",
            )
        return forecast_next_month(costs)
