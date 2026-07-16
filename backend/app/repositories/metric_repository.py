"""Data-access layer for the Metric entity."""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.metric import Metric
from app.repositories.base_repository import BaseRepository


class MetricRepository(BaseRepository[Metric]):
    def __init__(self, db: Session):
        super().__init__(db, Metric)

    def search(
        self,
        deployment_id: int,
        metric_type: str | None,
        since: datetime | None,
        until: datetime | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Metric], int]:
        stmt = select(Metric).where(Metric.deployment_id == deployment_id)
        count_stmt = (
            select(func.count()).select_from(Metric).where(Metric.deployment_id == deployment_id)
        )

        if metric_type:
            condition = Metric.metric_type == metric_type
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if since:
            condition = Metric.recorded_at >= since
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if until:
            condition = Metric.recorded_at <= until
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        stmt = stmt.order_by(Metric.recorded_at.desc()).offset(offset).limit(limit)

        items = list(self.db.scalars(stmt).all())
        total = self.db.scalar(count_stmt) or 0
        return items, total
