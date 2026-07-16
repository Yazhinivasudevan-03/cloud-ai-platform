"""Data-access layer for the AnomalyDetection entity (read-only from the API's
perspective; rows are written by the ml-models batch pipeline)."""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.anomaly_detection import AnomalyDetection
from app.repositories.base_repository import BaseRepository


class AnomalyDetectionRepository(BaseRepository[AnomalyDetection]):
    def __init__(self, db: Session):
        super().__init__(db, AnomalyDetection)

    def search(
        self,
        deployment_id: int,
        is_anomaly: bool | None,
        since: datetime | None,
        until: datetime | None,
        offset: int,
        limit: int,
    ) -> tuple[list[AnomalyDetection], int]:
        stmt = select(AnomalyDetection).where(AnomalyDetection.deployment_id == deployment_id)
        count_stmt = (
            select(func.count())
            .select_from(AnomalyDetection)
            .where(AnomalyDetection.deployment_id == deployment_id)
        )

        if is_anomaly is not None:
            condition = AnomalyDetection.is_anomaly == is_anomaly
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if since:
            condition = AnomalyDetection.detected_at >= since
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if until:
            condition = AnomalyDetection.detected_at <= until
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        stmt = stmt.order_by(AnomalyDetection.detected_at.desc()).offset(offset).limit(limit)

        items = list(self.db.scalars(stmt).all())
        total = self.db.scalar(count_stmt) or 0
        return items, total
