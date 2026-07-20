"""Data-access layer for the ResourceUsage entity."""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.resource_usage import ResourceUsage
from app.repositories.base_repository import BaseRepository


class ResourceUsageRepository(BaseRepository[ResourceUsage]):
    def __init__(self, db: Session):
        super().__init__(db, ResourceUsage)

    def get_latest_for_deployment(self, deployment_id: int) -> ResourceUsage | None:
        stmt = (
            select(ResourceUsage)
            .where(ResourceUsage.deployment_id == deployment_id)
            .order_by(ResourceUsage.recorded_at.desc())
            .limit(1)
        )
        return self.db.scalars(stmt).first()

    def search(
        self,
        deployment_id: int,
        since: datetime | None,
        until: datetime | None,
        offset: int,
        limit: int,
    ) -> tuple[list[ResourceUsage], int]:
        stmt = select(ResourceUsage).where(ResourceUsage.deployment_id == deployment_id)
        count_stmt = (
            select(func.count())
            .select_from(ResourceUsage)
            .where(ResourceUsage.deployment_id == deployment_id)
        )

        if since:
            condition = ResourceUsage.recorded_at >= since
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if until:
            condition = ResourceUsage.recorded_at <= until
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        stmt = stmt.order_by(ResourceUsage.recorded_at.desc()).offset(offset).limit(limit)

        items = list(self.db.scalars(stmt).all())
        total = self.db.scalar(count_stmt) or 0
        return items, total
