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
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models.alert import Alert
from app.models.anomaly_detection import AnomalyDetection
from app.models.cloud_account_alert_threshold import CloudAccountAlertThreshold
from app.models.cloud_cost import CloudCost
from app.models.cloud_provider_account import CloudProviderAccount
from app.models.deployment import Deployment
from app.models.failure_prediction import FailurePrediction
from app.models.project import Project
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
        project_ids = list(self.db.scalars(select(Project.id)).all())

        alerts_created = 0
        alerts_resolved = 0
        notifications_sent = 0

        for deployment_id in deployment_ids:
            created, resolved, notified = self._evaluate_deployment(deployment_id)
            alerts_created += created
            alerts_resolved += resolved
            notifications_sent += notified

        for project_id in project_ids:
            created, resolved, notified = self._evaluate_project_cost(project_id)
            alerts_created += created
            alerts_resolved += resolved
            notifications_sent += notified

        return {
            "deployments_evaluated": len(deployment_ids),
            "projects_evaluated": len(project_ids),
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

    def _evaluate_project_cost(self, project_id: int) -> tuple[int, int, int]:
        """Cost alerting (Phase 21) is project-scoped, not deployment-scoped
        - spend is tracked per-project via CloudCost - so this mirrors
        `_evaluate_deployment`'s create/resolve idempotent lifecycle but
        against `Alert.project_id` instead of `deployment_id`, and against
        a single cost condition rather than a list of conditions (a
        project either has one active cost tier or none)."""
        project = self.db.get(Project, project_id)
        condition = self._project_cost_condition(project)
        desired_types = {condition.alert_type} if condition is not None else set()

        alerts_created = 0
        alerts_resolved = 0
        notifications_sent = 0
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        for existing in self.repository.list_active_for_project(project_id):
            if existing.alert_type not in desired_types:
                existing.status = "resolved"
                existing.resolved_at = now
                alerts_resolved += 1

        if condition is not None:
            existing = self.repository.get_active_for_project(project_id, condition.alert_type)
            if existing is None or existing.severity != condition.severity:
                if existing is not None and existing.severity != condition.severity:
                    existing.status = "resolved"
                    existing.resolved_at = now
                    alerts_resolved += 1

                alert = Alert(
                    project_id=project_id,
                    deployment_id=None,
                    alert_type=condition.alert_type,
                    severity=condition.severity,
                    threshold_percent=condition.threshold_percent,
                    message=condition.message,
                    status="active",
                    triggered_at=now,
                )
                self.db.add(alert)
                self.db.flush()
                alerts_created += 1
                notifications_sent += dispatch(self.db, alert)

        self.db.commit()
        return alerts_created, alerts_resolved, notifications_sent

    def _project_cost_condition(self, project: Project) -> _Condition | None:
        """Skipped entirely when the project has no configured
        monthly_budget - the same guard every other limit-based condition
        in this service uses. Spend is summed from real CloudCost rows
        whose billing_period_start falls in the current calendar month
        (matching how the Cost Explorer sync - Phase 19 - creates one row
        per service per month with billing_period_start on the 1st)."""
        if not project.monthly_budget or project.monthly_budget <= 0:
            return None

        today = datetime.now(timezone.utc).date()
        month_start = date(today.year, today.month, 1)
        next_month_start = date(today.year + (today.month // 12), (today.month % 12) + 1, 1)

        spend = self.db.scalar(
            select(func.sum(CloudCost.cost_amount)).where(
                CloudCost.project_id == project.id,
                CloudCost.billing_period_start >= month_start,
                CloudCost.billing_period_start < next_month_start,
            )
        )
        spend = float(spend) if spend is not None else 0.0
        percent = (spend / project.monthly_budget) * 100

        warning = (
            project.cost_warning_threshold
            if project.cost_warning_threshold is not None
            else self.settings.ALERT_COST_WARNING_THRESHOLD
        )
        critical = (
            project.cost_critical_threshold
            if project.cost_critical_threshold is not None
            else self.settings.ALERT_COST_CRITICAL_THRESHOLD
        )
        saturated = (
            project.cost_saturated_threshold
            if project.cost_saturated_threshold is not None
            else self.settings.ALERT_COST_SATURATED_THRESHOLD
        )

        if percent >= saturated:
            return _Condition(
                alert_type="cost_saturated",
                severity="critical",
                threshold_percent=saturated,
                message=(
                    f"Monthly spend is {spend:.2f} ({percent:.1f}% of the "
                    f"{project.monthly_budget:.2f} budget) - at or over budget"
                ),
            )
        if percent >= critical:
            return _Condition(
                alert_type="cost_high",
                severity="critical",
                threshold_percent=critical,
                message=(
                    f"Monthly spend is {spend:.2f} ({percent:.1f}% of the "
                    f"{project.monthly_budget:.2f} budget) - above critical threshold"
                ),
            )
        if percent >= warning:
            return _Condition(
                alert_type="cost_elevated",
                severity="warning",
                threshold_percent=warning,
                message=(
                    f"Monthly spend is {spend:.2f} ({percent:.1f}% of the "
                    f"{project.monthly_budget:.2f} budget) - above warning threshold"
                ),
            )
        return None

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

            memory_condition = self._limit_based_condition(
                "memory", "Memory", latest_usage.memory_usage_mb, deployment.memory_limit_mb, threshold_override
            )
            if memory_condition is not None:
                conditions.append(memory_condition)

            disk_condition = self._limit_based_condition(
                "disk", "Disk", latest_usage.disk_usage_mb, deployment.disk_limit_mb, threshold_override
            )
            if disk_condition is not None:
                conditions.append(disk_condition)

            network_condition = self._limit_based_condition(
                "network",
                "Network",
                latest_usage.network_in_kbps + latest_usage.network_out_kbps,
                deployment.network_limit_kbps,
                threshold_override,
            )
            if network_condition is not None:
                conditions.append(network_condition)

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
        its own CPU/memory/disk/network threshold overrides (Phase 20-21) -
        null fields on that override still fall back to the platform-wide
        Settings default, resolved field-by-field in `_threshold()`."""
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

    def _limit_based_condition(
        self,
        metric: str,
        label: str,
        usage_value: float,
        limit_value: float | None,
        override: CloudAccountAlertThreshold | None,
    ) -> _Condition | None:
        """Shared 3-tier evaluation for any usage-vs-configured-limit metric
        (memory, disk, network - Phase 20/21) - skipped entirely when no
        limit is configured, since the raw usage value alone can't be
        turned into a utilization percentage without one to divide by (the
        same guard OptimizationService's memory recommendations already
        use). `metric` must match the lowercase prefix of both the
        ALERT_<METRIC>_*_THRESHOLD settings and the CloudAccountAlertThreshold
        override column names, e.g. "memory" -> ALERT_MEMORY_WARNING_THRESHOLD
        / memory_warning_threshold."""
        if not limit_value or limit_value <= 0:
            return None
        percent = (usage_value / limit_value) * 100

        warning = self._threshold(
            override, f"{metric}_warning_threshold", getattr(self.settings, f"ALERT_{metric.upper()}_WARNING_THRESHOLD")
        )
        critical = self._threshold(
            override, f"{metric}_critical_threshold", getattr(self.settings, f"ALERT_{metric.upper()}_CRITICAL_THRESHOLD")
        )
        saturated = self._threshold(
            override, f"{metric}_saturated_threshold", getattr(self.settings, f"ALERT_{metric.upper()}_SATURATED_THRESHOLD")
        )

        if percent >= saturated:
            return _Condition(
                alert_type=f"{metric}_saturated",
                severity="critical",
                threshold_percent=saturated,
                message=f"{label} usage at {percent:.1f}% of the configured limit - at capacity",
            )
        if percent >= critical:
            return _Condition(
                alert_type=f"{metric}_high",
                severity="critical",
                threshold_percent=critical,
                message=f"{label} usage at {percent:.1f}% of the configured limit - above critical threshold",
            )
        if percent >= warning:
            return _Condition(
                alert_type=f"{metric}_elevated",
                severity="warning",
                threshold_percent=warning,
                message=f"{label} usage at {percent:.1f}% of the configured limit - above warning threshold",
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
