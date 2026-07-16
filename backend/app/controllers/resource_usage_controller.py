"""Controller layer for ResourceUsage ingestion/query endpoints."""
import math
from datetime import datetime

from sqlalchemy.orm import Session

from app.schemas.common import PaginatedResponse, PaginationMeta
from app.schemas.resource_usage import ResourceUsageCreate, ResourceUsageRead
from app.services.resource_usage_service import ResourceUsageService


class ResourceUsageController:
    def __init__(self, db: Session):
        self.service = ResourceUsageService(db)

    def ingest(self, deployment_id: int, payload: ResourceUsageCreate) -> ResourceUsageRead:
        usage = self.service.ingest(deployment_id, payload)
        return ResourceUsageRead.model_validate(usage)

    def list(
        self,
        deployment_id: int,
        since: datetime | None,
        until: datetime | None,
        page: int,
        page_size: int,
    ) -> PaginatedResponse[ResourceUsageRead]:
        items, total = self.service.list(deployment_id, since, until, page, page_size)
        total_pages = math.ceil(total / page_size) if page_size else 0
        return PaginatedResponse[ResourceUsageRead](
            items=[ResourceUsageRead.model_validate(i) for i in items],
            meta=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=total_pages
            ),
        )
