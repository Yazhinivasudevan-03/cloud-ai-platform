"""Controller layer for Metric ingestion/query endpoints."""
import math
from datetime import datetime

from sqlalchemy.orm import Session

from app.schemas.common import PaginatedResponse, PaginationMeta
from app.schemas.metric import MetricCreate, MetricRead
from app.services.metric_service import MetricService


class MetricController:
    def __init__(self, db: Session):
        self.service = MetricService(db)

    def ingest(self, deployment_id: int, payload: MetricCreate) -> MetricRead:
        metric = self.service.ingest(deployment_id, payload)
        return MetricRead.model_validate(metric)

    def list(
        self,
        deployment_id: int,
        metric_type: str | None,
        since: datetime | None,
        until: datetime | None,
        page: int,
        page_size: int,
    ) -> PaginatedResponse[MetricRead]:
        items, total = self.service.list(deployment_id, metric_type, since, until, page, page_size)
        total_pages = math.ceil(total / page_size) if page_size else 0
        return PaginatedResponse[MetricRead](
            items=[MetricRead.model_validate(i) for i in items],
            meta=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=total_pages
            ),
        )
