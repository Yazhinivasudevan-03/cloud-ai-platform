"""Rule engine evaluating recent resource_usage into OptimizationRecommendation
rows, with the same idempotent create/auto-dismiss lifecycle pattern as
Phase 5's AlertEvaluationService: a pending recommendation is not re-created
every run while its condition still holds, and is auto-dismissed once the
condition clears.

Recommendations are also prediction-informed (see `_blend_with_forecast`),
not purely reactive to past actuals - closing a real gap between this
platform's own architecture diagram (which shows "AI predicts usage" as an
input to "recommend resource allocation") and what the code previously did
(the recommendation engine never looked at the LSTM's own `Prediction`
table at all).
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
from app.repositories.prediction_repository import PredictionRepository
from app.schemas.optimization_recommendation import OptimizationRecommendationStatus
from app.utils.exceptions import ConflictError, NotFoundError

_CPU_RECOMMENDATION_TYPES = {"increase_pods", "increase_cpu", "scale_deployment", "reduce_pods", "reduce_cpu"}
_MEMORY_RECOMMENDATION_TYPES = {"increase_memory", "reduce_memory"}


class OptimizationService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = OptimizationRecommendationRepository(db)
        self.deployment_repository = DeploymentRepository(db)
        self.prediction_repository = PredictionRepository(db)
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
        recommendations_auto_applied = 0

        for deployment_id in deployment_ids:
            created, dismissed, auto_applied = self._evaluate_deployment(deployment_id)
            recommendations_created += created
            recommendations_dismissed += dismissed
            recommendations_auto_applied += auto_applied

        return {
            "deployments_evaluated": len(deployment_ids),
            "recommendations_created": recommendations_created,
            "recommendations_dismissed": recommendations_dismissed,
            "recommendations_auto_applied": recommendations_auto_applied,
        }

    def _evaluate_deployment(self, deployment_id: int) -> tuple[int, int, int]:
        deployment = self.db.get(Deployment, deployment_id)
        window = self._recent_usage_window(deployment_id)
        if not window:
            return 0, 0, 0

        avg_cpu = sum(row.cpu_usage_percent for row in window) / len(window)
        avg_memory = sum(row.memory_usage_mb for row in window) / len(window)

        effective_cpu, cpu_note = self._blend_with_forecast(deployment_id, "cpu_usage_percent", avg_cpu)
        effective_memory, memory_note = self._blend_with_forecast(
            deployment_id, "memory_usage_mb", avg_memory
        )

        conditions = evaluate_recommendations(
            avg_cpu_usage_percent=effective_cpu,
            avg_memory_usage_mb=effective_memory,
            memory_limit_mb=deployment.memory_limit_mb,
            replicas=deployment.replicas,
        )
        desired_types = {c.recommendation_type for c in conditions}

        recommendations_created = 0
        recommendations_dismissed = 0
        recommendations_auto_applied = 0

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

            description = condition.description
            if condition.recommendation_type in _CPU_RECOMMENDATION_TYPES and cpu_note:
                description = f"{description} {cpu_note}"
            elif condition.recommendation_type in _MEMORY_RECOMMENDATION_TYPES and memory_note:
                description = f"{description} {memory_note}"

            status = "pending"
            if self._auto_apply(deployment, condition):
                status = "applied"
                description = f"{description} (auto-applied)"
                recommendations_auto_applied += 1

            self.db.add(
                OptimizationRecommendation(
                    deployment_id=deployment_id,
                    recommendation_type=condition.recommendation_type,
                    description=description,
                    estimated_savings=None,
                    status=status,
                )
            )
            recommendations_created += 1

        if any_decrease and self._create_cost_recommendation(deployment, cooldown_since):
            recommendations_created += 1

        self.db.commit()
        return recommendations_created, recommendations_dismissed, recommendations_auto_applied

    def _auto_apply(self, deployment: Deployment, condition) -> bool:
        """Writes a recommendation's concrete target straight onto the
        Deployment record and reports whether it did - only for types with
        a real, already safety-bounded numeric target (see
        RecommendationCondition), and only when OPTIMIZATION_AUTO_APPLY_ENABLED
        is on and this specific type is in the configured auto-apply set.

        There is no live Kubernetes API integration in this platform (see
        docs/PHASE_8.md) - this updates this platform's own record of the
        deployment's desired replicas/memory limit, not a real cluster's
        actual Deployment object. The next scheduled evaluation re-reads
        these same fields, so an auto-applied change is self-correcting:
        if it overshoots or undershoots, the following run recommends
        (and, if still enabled, auto-applies) a further adjustment.
        """
        if not self.settings.OPTIMIZATION_AUTO_APPLY_ENABLED:
            return False
        if condition.recommendation_type not in self.settings.optimization_auto_apply_types_set:
            return False

        if condition.target_replicas is not None:
            deployment.replicas = condition.target_replicas
            return True
        if condition.target_memory_limit_mb is not None:
            deployment.memory_limit_mb = condition.target_memory_limit_mb
            return True
        return False

    def _blend_with_forecast(
        self, deployment_id: int, metric_type: str, actual_value: float
    ) -> tuple[float, str | None]:
        """Returns the higher of (recent actual average, latest confident
        LSTM forecast) for this metric, plus a human-readable note when the
        forecast is what determined the result - so a recommendation
        triggered by a predicted future spike (rather than what's actually
        happening right now) says so plainly, instead of silently reading
        like a purely reactive one.

        Taking the max (not an average or the forecast alone) means a
        confident high forecast can both trigger a scale-up recommendation
        proactively, and prevent a scale-down recommendation from firing
        right before a predicted spike - both are the correct call for the
        same reason.
        """
        prediction = self.prediction_repository.get_latest_for_metric(deployment_id, metric_type)
        if (
            prediction is None
            or prediction.confidence_score < self.settings.OPTIMIZATION_PREDICTION_CONFIDENCE_THRESHOLD
            or prediction.predicted_value <= actual_value
        ):
            return actual_value, None

        note = (
            f"(LSTM forecasts {prediction.predicted_value:.1f} for {metric_type} in the next "
            f"window, confidence {prediction.confidence_score:.0%} - higher than the recent "
            f"actual average, so this recommendation is forecast-driven.)"
        )
        return prediction.predicted_value, note

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
