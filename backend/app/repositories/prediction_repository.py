"""Data-access layer for the Prediction entity (read-only from the API's perspective;
rows are written by the ml-models batch pipeline, not through this backend)."""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.prediction import Prediction
from app.repositories.base_repository import BaseRepository


class PredictionRepository(BaseRepository[Prediction]):
    def __init__(self, db: Session):
        super().__init__(db, Prediction)

    def get_latest_for_metric(self, deployment_id: int, metric_type: str) -> Prediction | None:
        """Most recent LSTM forecast for one metric - used to make resource
        optimization recommendations prediction-informed (see
        app/services/optimization_service.py), not just reactive to past
        actuals."""
        stmt = (
            select(Prediction)
            .where(Prediction.deployment_id == deployment_id, Prediction.metric_type == metric_type)
            .order_by(Prediction.generated_at.desc())
            .limit(1)
        )
        return self.db.scalars(stmt).first()

    def search(
        self,
        deployment_id: int,
        metric_type: str | None,
        model_type: str | None,
        since: datetime | None,
        until: datetime | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Prediction], int]:
        stmt = select(Prediction).where(Prediction.deployment_id == deployment_id)
        count_stmt = (
            select(func.count())
            .select_from(Prediction)
            .where(Prediction.deployment_id == deployment_id)
        )

        if metric_type:
            condition = Prediction.metric_type == metric_type
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if model_type:
            condition = Prediction.model_type == model_type
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if since:
            condition = Prediction.target_timestamp >= since
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if until:
            condition = Prediction.target_timestamp <= until
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        stmt = stmt.order_by(Prediction.target_timestamp.desc()).offset(offset).limit(limit)

        items = list(self.db.scalars(stmt).all())
        total = self.db.scalar(count_stmt) or 0
        return items, total
