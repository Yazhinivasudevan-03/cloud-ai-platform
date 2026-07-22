"""Controller layer for CloudCost ingestion/query/forecast endpoints."""
import math
from datetime import date

from sqlalchemy.orm import Session

from app.schemas.cloud_cost import CloudCostCreate, CloudCostRead, CostForecastRead
from app.schemas.common import PaginatedResponse, PaginationMeta
from app.services.cloud_cost_service import CloudCostService


class CloudCostController:
    def __init__(self, db: Session):
        self.service = CloudCostService(db)

    def ingest(self, project_id: int, payload: CloudCostCreate) -> CloudCostRead:
        cost = self.service.ingest(project_id, payload)
        return CloudCostRead.model_validate(cost)

    def list(
        self,
        project_id: int,
        provider: str | None,
        since: date | None,
        until: date | None,
        page: int,
        page_size: int,
    ) -> PaginatedResponse[CloudCostRead]:
        items, total = self.service.list(project_id, provider, since, until, page, page_size)
        total_pages = math.ceil(total / page_size) if page_size else 0
        return PaginatedResponse[CloudCostRead](
            items=[CloudCostRead.model_validate(i) for i in items],
            meta=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=total_pages
            ),
        )

    def forecast(self, project_id: int) -> CostForecastRead:
        forecast = self.service.forecast(project_id)
        return CostForecastRead(
            predicted_next_month_cost=forecast.predicted_next_month_cost,
            currency=forecast.currency,
            method=forecast.method,
            historical_periods_used=forecast.historical_periods_used,
            trend_slope_per_month=forecast.trend_slope_per_month,
        )

    def sync_from_aws(
        self, project_id: int, cloud_provider_account_id: int, current_user_id: int
    ) -> "list[CloudCostRead]":
        costs = self.service.sync_from_aws(project_id, cloud_provider_account_id, current_user_id)
        return [CloudCostRead.model_validate(c) for c in costs]
