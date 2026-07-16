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

        latest_usage = self.db.scalars(
            select(ResourceUsage)
            .where(ResourceUsage.deployment_id == deployment_id)
            .order_by(ResourceUsage.recorded_at.desc())
            .limit(1)
        ).first()
        if latest_usage is not None:
            cpu_condition = self._cpu_condition(latest_usage.cpu_usage_percent)
            if cpu_condition is not None:
                conditions.append(cpu_condition)

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

    def _cpu_condition(self, cpu_usage_percent: float) -> _Condition | None:
        if cpu_usage_percent >= self.settings.ALERT_CPU_SATURATED_THRESHOLD:
            return _Condition(
                alert_type="cpu_saturated",
                severity="critical",
                threshold_percent=self.settings.ALERT_CPU_SATURATED_THRESHOLD,
                message=f"CPU usage at {cpu_usage_percent:.1f}% - at capacity",
            )
        if cpu_usage_percent >= self.settings.ALERT_CPU_CRITICAL_THRESHOLD:
            return _Condition(
                alert_type="cpu_high",
                severity="critical",
                threshold_percent=self.settings.ALERT_CPU_CRITICAL_THRESHOLD,
                message=f"CPU usage at {cpu_usage_percent:.1f}% - above critical threshold",
            )
        if cpu_usage_percent >= self.settings.ALERT_CPU_WARNING_THRESHOLD:
            return _Condition(
                alert_type="cpu_elevated",
                severity="warning",
                threshold_percent=self.settings.ALERT_CPU_WARNING_THRESHOLD,
                message=f"CPU usage at {cpu_usage_percent:.1f}% - above warning threshold",
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
