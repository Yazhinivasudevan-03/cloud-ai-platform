"""Data-access layer for the CloudCost entity."""
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cloud_cost import CloudCost
from app.repositories.base_repository import BaseRepository


class CloudCostRepository(BaseRepository[CloudCost]):
    def __init__(self, db: Session):
        super().__init__(db, CloudCost)

    def search(
        self,
        project_id: int,
        provider: str | None,
        since: date | None,
        until: date | None,
        offset: int,
        limit: int,
    ) -> tuple[list[CloudCost], int]:
        stmt = select(CloudCost).where(CloudCost.project_id == project_id)
        count_stmt = (
            select(func.count()).select_from(CloudCost).where(CloudCost.project_id == project_id)
        )

        if provider:
            condition = CloudCost.provider == provider
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if since:
            condition = CloudCost.billing_period_start >= since
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if until:
            condition = CloudCost.billing_period_end <= until
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        stmt = stmt.order_by(CloudCost.billing_period_start.desc()).offset(offset).limit(limit)

        items = list(self.db.scalars(stmt).all())
        total = self.db.scalar(count_stmt) or 0
        return items, total

    def list_all_for_project(self, project_id: int) -> list[CloudCost]:
        stmt = (
            select(CloudCost)
            .where(CloudCost.project_id == project_id)
            .order_by(CloudCost.billing_period_start)
        )
        return list(self.db.scalars(stmt).all())
