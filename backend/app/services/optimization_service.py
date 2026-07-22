"""Rule engine evaluating recent resource_usage into OptimizationRecommendation
rows, with the same idempotent create/auto-dismiss lifecycle pattern as
Phase 5's AlertEvaluationService: a pending recommendation is not re-created
every run while its condition still holds, and is auto-dismissed once the
condition clears.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models.cloud_cost import CloudCost
from app.models.deployment import Deployment
from app.models.optimization_recommendation import OptimizationRecommendation
from app.models.resource_usage import ResourceUsage
from app.optimization.cost_forecaster import aggregate_by_month
from app.optimization.recommendation_engine import evaluate as evaluate_recommendations
from app.repositories.deployment_repository import DeploymentRepository
from app.repositories.optimization_recommendation_repository import (
    OptimizationRecommendationRepository,
)
from app.schemas.optimization_recommendation import OptimizationRecommendationStatus
from app.utils.exceptions import ConflictError, NotFoundError


class OptimizationService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = OptimizationRecommendationRepository(db)
        self.deployment_repository = DeploymentRepository(db)
        self.settings = get_settings()

    def get(self, recommendation_id: int) -> OptimizationRecommendation:
        recommendation = self.repository.get_by_id(recommendation_id)
        if recommendation is None:
            raise NotFoundError(
                f"Optimization recommendation {recommendation_id} not found",
                code="OPTIMIZATION_RECOMMENDATION_NOT_FOUND",
            )
        return recommendation

    def list_for_deployment(
        self,
        deployment_id: int,
        status: str | None,
        recommendation_type: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[OptimizationRecommendation], int]:
        if self.deployment_repository.get_by_id(deployment_id) is None:
            raise NotFoundError(
                f"Deployment {deployment_id} not found", code="DEPLOYMENT_NOT_FOUND"
            )
        offset = (page - 1) * page_size
        return self.repository.search(deployment_id, status, recommendation_type, offset, page_size)

    def list_global(
        self,
        deployment_id: int | None,
        status: str | None,
        recommendation_type: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[OptimizationRecommendation], int]:
        """Cross-deployment listing for dashboard-level views - `deployment_id`
        is an optional filter here, not a required scope."""
        if deployment_id is not None and self.deployment_repository.get_by_id(deployment_id) is None:
            raise NotFoundError(
                f"Deployment {deployment_id} not found", code="DEPLOYMENT_NOT_FOUND"
            )
        offset = (page - 1) * page_size
        return self.repository.search(deployment_id, status, recommendation_type, offset, page_size)

    def update_status(
        self, recommendation_id: int, new_status: OptimizationRecommendationStatus
    ) -> OptimizationRecommendation:
        recommendation = self.get(recommendation_id)
        if recommendation.status != "pending":
            raise ConflictError(
                f"Cannot transition recommendation from '{recommendation.status}' to "
                f"'{new_status.value}' - only pending recommendations can be actioned",
                code="INVALID_RECOMMENDATION_TRANSITION",
            )
        recommendation.status = new_status.value
        self.db.commit()
        self.db.refresh(recommendation)
        return recommendation

    def evaluate_all(self) -> dict:
        deployment_ids = list(self.db.scalars(select(Deployment.id)).all())

        recommendations_created = 0
        recommendations_dismissed = 0

        for deployment_id in deployment_ids:
            created, dismissed = self._evaluate_deployment(deployment_id)
            recommendations_created += created
            recommendations_dismissed += dismissed

        return {
            "deployments_evaluated": len(deployment_ids),
            "recommendations_created": recommendations_created,
            "recommendations_dismissed": recommendations_dismissed,
        }

    def _evaluate_deployment(self, deployment_id: int) -> tuple[int, int]:
        deployment = self.db.get(Deployment, deployment_id)
        window = self._recent_usage_window(deployment_id)
        if not window:
            return 0, 0

        avg_cpu = sum(row.cpu_usage_percent for row in window) / len(window)
        avg_memory = sum(row.memory_usage_mb for row in window) / len(window)

        conditions = evaluate_recommendations(
            avg_cpu_usage_percent=avg_cpu,
            avg_memory_usage_mb=avg_memory,
            memory_limit_mb=deployment.memory_limit_mb,
            replicas=deployment.replicas,
        )
        desired_types = {c.recommendation_type for c in conditions}

        recommendations_created = 0
        recommendations_dismissed = 0

        for existing in self.repository.list_pending_for_deployment(deployment_id):
            if existing.recommendation_type not in desired_types:
                existing.status = "dismissed"
                recommendations_dismissed += 1

        cooldown_since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            minutes=self.settings.OPTIMIZATION_RECOMMENDATION_COOLDOWN_MINUTES
        )

        any_decrease = False
        for condition in conditions:
            if condition.direction == "decrease":
                any_decrease = True
            if self.repository.get_pending(deployment_id, condition.recommendation_type):
                continue  # already recommending this - no duplicate
            if self.repository.get_recently_resolved(
                deployment_id, condition.recommendation_type, cooldown_since
            ):
                continue  # dismissed/applied too recently - within cooldown, don't re-nag
            self.db.add(
                OptimizationRecommendation(
                    deployment_id=deployment_id,
                    recommendation_type=condition.recommendation_type,
                    description=condition.description,
                    estimated_savings=None,
                    status="pending",
                )
            )
            recommendations_created += 1

        if any_decrease and self._create_cost_recommendation(deployment, cooldown_since):
            recommendations_created += 1

        self.db.commit()
        return recommendations_created, recommendations_dismissed

    def _recent_usage_window(self, deployment_id: int) -> list[ResourceUsage]:
        stmt = (
            select(ResourceUsage)
            .where(ResourceUsage.deployment_id == deployment_id)
            .order_by(ResourceUsage.recorded_at.desc())
            .limit(self.settings.OPTIMIZATION_LOOKBACK_ROWS)
        )
        return list(self.db.scalars(stmt).all())

    def _create_cost_recommendation(self, deployment: Deployment, cooldown_since: datetime) -> bool:
        if self.repository.get_pending(deployment.id, "optimize_cost"):
            return False
        if self.repository.get_recently_resolved(deployment.id, "optimize_cost", cooldown_since):
            return False

        project_id = deployment.microservice.project_id
        costs = list(
            self.db.scalars(select(CloudCost).where(CloudCost.project_id == project_id)).all()
        )

        if costs:
            monthly = aggregate_by_month(costs)
            latest_month_total = monthly[-1][1]
            fraction = self.settings.OPTIMIZATION_COST_RIGHTSIZING_SAVINGS_FRACTION
            estimated_savings = round(latest_month_total * fraction, 2)
            description = (
                f"Rightsizing this deployment could save an estimated "
                f"{estimated_savings} {costs[0].currency}/month (~{fraction:.0%} of the "
                f"project's most recent monthly spend of {latest_month_total:.2f} "
                f"{costs[0].currency})."
            )
        else:
            estimated_savings = None
            description = (
                "Rightsizing this deployment would reduce cost, but no cloud_costs "
                "history exists for this project yet to estimate a specific amount."
            )

        self.db.add(
            OptimizationRecommendation(
                deployment_id=deployment.id,
                recommendation_type="optimize_cost",
                description=description,
                estimated_savings=estimated_savings,
                status="pending",
            )
        )
        return True
