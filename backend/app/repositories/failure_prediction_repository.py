"""Data-access layer for the FailurePrediction entity (read-only from the API's
perspective; rows are written by the ml-models batch pipeline)."""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.failure_prediction import FailurePrediction
from app.repositories.base_repository import BaseRepository


class FailurePredictionRepository(BaseRepository[FailurePrediction]):
    def __init__(self, db: Session):
        super().__init__(db, FailurePrediction)

    def search(
        self,
        deployment_id: int,
        failure_type: str | None,
        since: datetime | None,
        until: datetime | None,
        offset: int,
        limit: int,
    ) -> tuple[list[FailurePrediction], int]:
        stmt = select(FailurePrediction).where(FailurePrediction.deployment_id == deployment_id)
        count_stmt = (
            select(func.count())
            .select_from(FailurePrediction)
            .where(FailurePrediction.deployment_id == deployment_id)
        )

        if failure_type:
            condition = FailurePrediction.failure_type == failure_type
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if since:
            condition = FailurePrediction.predicted_at >= since
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if until:
            condition = FailurePrediction.predicted_at <= until
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        stmt = stmt.order_by(FailurePrediction.predicted_at.desc()).offset(offset).limit(limit)

        items = list(self.db.scalars(stmt).all())
        total = self.db.scalar(count_stmt) or 0
        return items, total
