"""Data-access layer for the OptimizationRecommendation entity."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.optimization_recommendation import OptimizationRecommendation
from app.repositories.base_repository import BaseRepository


class OptimizationRecommendationRepository(BaseRepository[OptimizationRecommendation]):
    def __init__(self, db: Session):
        super().__init__(db, OptimizationRecommendation)

    def get_pending(
        self, deployment_id: int, recommendation_type: str
    ) -> OptimizationRecommendation | None:
        stmt = select(OptimizationRecommendation).where(
            OptimizationRecommendation.deployment_id == deployment_id,
            OptimizationRecommendation.recommendation_type == recommendation_type,
            OptimizationRecommendation.status == "pending",
        )
        return self.db.scalars(stmt).first()

    def list_pending_for_deployment(
        self, deployment_id: int
    ) -> list[OptimizationRecommendation]:
        stmt = select(OptimizationRecommendation).where(
            OptimizationRecommendation.deployment_id == deployment_id,
            OptimizationRecommendation.status == "pending",
        )
        return list(self.db.scalars(stmt).all())

    def search(
        self,
        deployment_id: int | None,
        status: str | None,
        recommendation_type: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[OptimizationRecommendation], int]:
        """deployment_id=None searches across all deployments (the global
        `GET /optimization-recommendations` listing); a specific ID scopes to
        one deployment."""
        stmt = select(OptimizationRecommendation)
        count_stmt = select(func.count()).select_from(OptimizationRecommendation)

        if deployment_id is not None:
            condition = OptimizationRecommendation.deployment_id == deployment_id
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if status:
            condition = OptimizationRecommendation.status == status
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if recommendation_type:
            condition = OptimizationRecommendation.recommendation_type == recommendation_type
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        stmt = stmt.order_by(OptimizationRecommendation.created_at.desc()).offset(offset).limit(limit)

        items = list(self.db.scalars(stmt).all())
        total = self.db.scalar(count_stmt) or 0
        return items, total
