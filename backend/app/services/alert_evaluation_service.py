"""Rule engine evaluating recent telemetry (resource usage) and Phase 4 AI
output (anomaly detections, failure predictions) into `Alert` rows, with an
idempotent create/resolve lifecycle and notification fan-out to admins.

Design note: "most recent row per deployment" is used as the evaluation
input, rather than a time-windowed lookback, so the engine is deterministic
and easy to test/demo against static (e.g. synthetic, backfilled) history. A
production deployment ingesting continuously would additionally want a
staleness check (e.g. ignore data older than N minutes so a deployment that
stopped reporting doesn't look artificially "fine" forever) - a natural
follow-up, intentionally not implemented here to keep this phase's scope to
what's actually verified.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models.alert import Alert
from app.models.anomaly_detection import AnomalyDetection
from app.models.cloud_account_alert_threshold import CloudAccountAlertThreshold
from app.models.cloud_provider_account import CloudProviderAccount
from app.models.deployment import Deployment
from app.models.failure_prediction import FailurePrediction
from app.models.resource_usage import ResourceUsage
from app.notifications.dispatcher import dispatch
from app.repositories.alert_repository import AlertRepository


@dataclass(frozen=True)
class _Condition:
    alert_type: str
    severity: str
    threshold_percent: float | None
    message: str


class AlertEvaluationService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AlertRepository(db)
        self.settings = get_settings()

    def evaluate_all(self) -> dict:
        deployment_ids = list(self.db.scalars(select(Deployment.id)).all())

        alerts_created = 0
        alerts_resolved = 0
        notifications_sent = 0

        for deployment_id in deployment_ids:
            created, resolved, notified = self._evaluate_deployment(deployment_id)
            alerts_created += created
            alerts_resolved += resolved
            notifications_sent += notified

        return {
            "deployments_evaluated": len(deployment_ids),
            "alerts_created": alerts_created,
            "alerts_resolved": alerts_resolved,
            "notifications_sent": notifications_sent,
        }

    def _evaluate_deployment(self, deployment_id: int) -> tuple[int, int, int]:
        desired = self._desired_conditions(deployment_id)
        desired_types = {c.alert_type for c in desired}

        alerts_created = 0
        alerts_resolved = 0
        notifications_sent = 0
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Resolve alerts whose triggering condition has cleared.
        for existing in self.repository.list_active_for_deployment(deployment_id):
            if existing.alert_type not in desired_types:
                existing.status = "resolved"
                existing.resolved_at = now
                alerts_resolved += 1

        # Create/refresh alerts for currently-triggered conditions.
        for condition in desired:
            existing = self.repository.get_active(deployment_id, condition.alert_type)
            if existing is not None and existing.severity == condition.severity:
                continue  # already alerting at the same severity - no-op

            if existing is not None and existing.severity != condition.severity:
                existing.status = "resolved"
                existing.resolved_at = now
                alerts_resolved += 1

            alert = Alert(
                deployment_id=deployment_id,
                alert_type=condition.alert_type,
                severity=condition.severity,
                threshold_percent=condition.threshold_percent,
                message=condition.message,
                status="active",
                triggered_at=now,
            )
            self.db.add(alert)
            self.db.flush()  # assign alert.id before dispatch() references it
            alerts_created += 1
            notifications_sent += dispatch(self.db, alert)

        self.db.commit()
        return alerts_created, alerts_resolved, notifications_sent

    def _desired_conditions(self, deployment_id: int) -> list[_Condition]:
        conditions: list[_Condition] = []
        deployment = self.db.get(Deployment, deployment_id)
        threshold_override = self._resolve_threshold_override(deployment)

        latest_usage = self.db.scalars(
            select(ResourceUsage)
            .where(ResourceUsage.deployment_id == deployment_id)
            .order_by(ResourceUsage.recorded_at.desc())
            .limit(1)
        ).first()
        if latest_usage is not None:
            cpu_condition = self._cpu_condition(latest_usage.cpu_usage_percent, threshold_override)
            if cpu_condition is not None:
                conditions.append(cpu_condition)

            memory_condition = self._memory_condition(
                latest_usage.memory_usage_mb, deployment.memory_limit_mb, threshold_override
            )
            if memory_condition is not None:
                conditions.append(memory_condition)

        latest_anomaly = self.db.scalars(
            select(AnomalyDetection)
            .where(AnomalyDetection.deployment_id == deployment_id)
            .order_by(AnomalyDetection.detected_at.desc())
            .limit(1)
        ).first()
        if latest_anomaly is not None and latest_anomaly.is_anomaly:
            conditions.append(
                _Condition(
                    alert_type="anomaly_detected",
                    severity="warning",
                    threshold_percent=None,
                    message=(
                        f"Isolation Forest flagged an anomaly (score="
                        f"{latest_anomaly.anomaly_score:.3f}) at "
                        f"{latest_anomaly.detected_at.isoformat()}"
                    ),
                )
            )

        latest_failure = self.db.scalars(
            select(FailurePrediction)
            .where(FailurePrediction.deployment_id == deployment_id)
            .order_by(FailurePrediction.predicted_at.desc())
            .limit(1)
        ).first()
        if latest_failure is not None:
            failure_condition = self._failure_condition(latest_failure)
            if failure_condition is not None:
                conditions.append(failure_condition)

        return conditions

    def _resolve_threshold_override(self, deployment: Deployment) -> CloudAccountAlertThreshold | None:
        """A deployment's linked cloud provider account (if any) may have
        its own CPU/memory threshold overrides (Phase 20) - null fields on
        that override still fall back to the platform-wide Settings
        default, resolved field-by-field in `_threshold()`."""
        if deployment.cloud_provider_account_id is None:
            return None
        account = self.db.get(CloudProviderAccount, deployment.cloud_provider_account_id)
        return account.alert_threshold if account is not None else None

    def _threshold(
        self, override: CloudAccountAlertThreshold | None, field: str, default: float
    ) -> float:
        if override is None:
            return default
        value = getattr(override, field)
        return value if value is not None else default

    def _cpu_condition(
        self, cpu_usage_percent: float, override: CloudAccountAlertThreshold | None
    ) -> _Condition | None:
        warning = self._threshold(override, "cpu_warning_threshold", self.settings.ALERT_CPU_WARNING_THRESHOLD)
        critical = self._threshold(override, "cpu_critical_threshold", self.settings.ALERT_CPU_CRITICAL_THRESHOLD)
        saturated = self._threshold(override, "cpu_saturated_threshold", self.settings.ALERT_CPU_SATURATED_THRESHOLD)

        if cpu_usage_percent >= saturated:
            return _Condition(
                alert_type="cpu_saturated",
                severity="critical",
                threshold_percent=saturated,
                message=f"CPU usage at {cpu_usage_percent:.1f}% - at capacity",
            )
        if cpu_usage_percent >= critical:
            return _Condition(
                alert_type="cpu_high",
                severity="critical",
                threshold_percent=critical,
                message=f"CPU usage at {cpu_usage_percent:.1f}% - above critical threshold",
            )
        if cpu_usage_percent >= warning:
            return _Condition(
                alert_type="cpu_elevated",
                severity="warning",
                threshold_percent=warning,
                message=f"CPU usage at {cpu_usage_percent:.1f}% - above warning threshold",
            )
        return None

    def _memory_condition(
        self,
        memory_usage_mb: float,
        memory_limit_mb: float | None,
        override: CloudAccountAlertThreshold | None,
    ) -> _Condition | None:
        """Skipped entirely when the deployment has no configured
        memory_limit_mb - memory_usage_mb alone can't be turned into a
        utilization percentage without a limit to divide by, the same
        guard OptimizationService's memory recommendations already use."""
        if not memory_limit_mb or memory_limit_mb <= 0:
            return None
        memory_percent = (memory_usage_mb / memory_limit_mb) * 100

        warning = self._threshold(
            override, "memory_warning_threshold", self.settings.ALERT_MEMORY_WARNING_THRESHOLD
        )
        critical = self._threshold(
            override, "memory_critical_threshold", self.settings.ALERT_MEMORY_CRITICAL_THRESHOLD
        )
        saturated = self._threshold(
            override, "memory_saturated_threshold", self.settings.ALERT_MEMORY_SATURATED_THRESHOLD
        )

        if memory_percent >= saturated:
            return _Condition(
                alert_type="memory_saturated",
                severity="critical",
                threshold_percent=saturated,
                message=f"Memory usage at {memory_percent:.1f}% of the configured limit - at capacity",
            )
        if memory_percent >= critical:
            return _Condition(
                alert_type="memory_high",
                severity="critical",
                threshold_percent=critical,
                message=f"Memory usage at {memory_percent:.1f}% of the configured limit - above critical threshold",
            )
        if memory_percent >= warning:
            return _Condition(
                alert_type="memory_elevated",
                severity="warning",
                threshold_percent=warning,
                message=f"Memory usage at {memory_percent:.1f}% of the configured limit - above warning threshold",
            )
        return None

    def _failure_condition(self, failure: FailurePrediction) -> _Condition | None:
        if failure.probability >= self.settings.ALERT_FAILURE_CRITICAL_THRESHOLD:
            severity = "critical"
        elif failure.probability >= self.settings.ALERT_FAILURE_WARNING_THRESHOLD:
            severity = "warning"
        else:
            return None
        return _Condition(
            alert_type="failure_risk",
            severity=severity,
            threshold_percent=None,
            message=(
                f"Random Forest predicts {failure.probability:.0%} probability of "
                f"{failure.failure_type} at {failure.predicted_at.isoformat()}"
            ),
        )
