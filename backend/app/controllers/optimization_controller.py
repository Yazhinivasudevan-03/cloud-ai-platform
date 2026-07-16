"""Controller layer for OptimizationRecommendation endpoints."""
import math

from sqlalchemy.orm import Session

from app.schemas.common import PaginatedResponse, PaginationMeta
from app.schemas.optimization_recommendation import (
    OptimizationEvaluationSummary,
    OptimizationRecommendationRead,
    OptimizationRecommendationStatus,
)
from app.services.optimization_service import OptimizationService


class OptimizationController:
    def __init__(self, db: Session):
        self.service = OptimizationService(db)

    def get(self, recommendation_id: int) -> OptimizationRecommendationRead:
        return OptimizationRecommendationRead.model_validate(self.service.get(recommendation_id))

    def list_for_deployment(
        self,
        deployment_id: int,
        status: str | None,
        recommendation_type: str | None,
        page: int,
        page_size: int,
    ) -> PaginatedResponse[OptimizationRecommendationRead]:
        items, total = self.service.list_for_deployment(
            deployment_id, status, recommendation_type, page, page_size
        )
        total_pages = math.ceil(total / page_size) if page_size else 0
        return PaginatedResponse[OptimizationRecommendationRead](
            items=[OptimizationRecommendationRead.model_validate(i) for i in items],
            meta=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=total_pages
            ),
        )

    def list_global(
        self,
        deployment_id: int | None,
        status: str | None,
        recommendation_type: str | None,
        page: int,
        page_size: int,
    ) -> PaginatedResponse[OptimizationRecommendationRead]:
        items, total = self.service.list_global(
            deployment_id, status, recommendation_type, page, page_size
        )
        total_pages = math.ceil(total / page_size) if page_size else 0
        return PaginatedResponse[OptimizationRecommendationRead](
            items=[OptimizationRecommendationRead.model_validate(i) for i in items],
            meta=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=total_pages
            ),
        )

    def update_status(
        self, recommendation_id: int, new_status: OptimizationRecommendationStatus
    ) -> OptimizationRecommendationRead:
        return OptimizationRecommendationRead.model_validate(
            self.service.update_status(recommendation_id, new_status)
        )

    def evaluate(self) -> OptimizationEvaluationSummary:
        summary = self.service.evaluate_all()
        return OptimizationEvaluationSummary(**summary)
