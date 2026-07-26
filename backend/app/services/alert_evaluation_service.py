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
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.integrations.kubernetes_monitor import list_unhealthy_containers, list_unhealthy_nodes
from app.integrations.prometheus_client import average_latency_ms, error_rate_percent
from app.models.alert import Alert
from app.models.anomaly_detection import AnomalyDetection
from app.models.audit_log import AuditLog
from app.models.cloud_account_alert_threshold import CloudAccountAlertThreshold
from app.models.cloud_cost import CloudCost
from app.models.cloud_provider_account import CloudProviderAccount
from app.models.deployment import Deployment
from app.models.failure_prediction import FailurePrediction
from app.models.pod import Pod
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

        security_created, security_resolved, security_notified = self._evaluate_security()
        alerts_created += security_created
        alerts_resolved += security_resolved
        notifications_sent += security_notified

        platform_created, platform_resolved, platform_notified = self._evaluate_platform_metrics()
        alerts_created += platform_created
        alerts_resolved += platform_resolved
        notifications_sent += platform_notified

        k8s_created, k8s_resolved, k8s_notified = self._evaluate_kubernetes()
        alerts_created += k8s_created
        alerts_resolved += k8s_resolved
        notifications_sent += k8s_notified

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

    def _evaluate_security(self) -> tuple[int, int, int]:
        """Security (Phase 23): real failed-login attempts, already
        captured by AuditLogMiddleware for every POST /api/v1/auth/login
        request (success or failure) since Phase 18 - no new logging
        added here, only a new query over existing rows. Per-user, not
        per-deployment/project (see Alert.user_id), counted in a rolling
        window so an old burst ages back out on its own even with zero
        new activity - the same idempotent create/resolve lifecycle every
        other alert type in this service already uses."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        window_start = now - timedelta(minutes=self.settings.ALERT_SECURITY_FAILED_LOGIN_WINDOW_MINUTES)

        failed_login_counts = dict(
            self.db.execute(
                select(AuditLog.user_id, func.count())
                .where(
                    AuditLog.action == "POST /api/v1/auth/login",
                    AuditLog.details == "status=401",
                    AuditLog.created_at >= window_start,
                    AuditLog.user_id.isnot(None),
                )
                .group_by(AuditLog.user_id)
            ).all()
        )
        active_user_ids = {
            alert.user_id
            for alert in self.db.scalars(
                select(Alert).where(Alert.alert_type.like("security_%"), Alert.status == "active")
            ).all()
        }
        user_ids = set(failed_login_counts) | active_user_ids

        alerts_created = 0
        alerts_resolved = 0
        notifications_sent = 0

        for user_id in user_ids:
            condition = self._security_condition(failed_login_counts.get(user_id, 0))
            desired_types = {condition.alert_type} if condition is not None else set()

            for existing in self.repository.list_active_for_user(user_id):
                if existing.alert_type not in desired_types:
                    existing.status = "resolved"
                    existing.resolved_at = now
                    alerts_resolved += 1

            if condition is not None:
                existing = self.repository.get_active_for_user(user_id, condition.alert_type)
                if existing is None:
                    alert = Alert(
                        user_id=user_id,
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

    def _security_condition(self, failed_login_count: int) -> _Condition | None:
        warning = self.settings.ALERT_SECURITY_FAILED_LOGIN_WARNING_THRESHOLD
        critical = self.settings.ALERT_SECURITY_FAILED_LOGIN_CRITICAL_THRESHOLD
        saturated = self.settings.ALERT_SECURITY_FAILED_LOGIN_SATURATED_THRESHOLD
        window = self.settings.ALERT_SECURITY_FAILED_LOGIN_WINDOW_MINUTES

        if failed_login_count >= saturated:
            return _Condition(
                alert_type="security_saturated",
                severity="critical",
                threshold_percent=saturated,
                message=(
                    f"{failed_login_count} failed login attempts in the last {window} minutes - "
                    f"at or above the saturated threshold ({saturated:.0f})"
                ),
            )
        if failed_login_count >= critical:
            return _Condition(
                alert_type="security_high",
                severity="critical",
                threshold_percent=critical,
                message=(
                    f"{failed_login_count} failed login attempts in the last {window} minutes - "
                    f"above the critical threshold ({critical:.0f})"
                ),
            )
        if failed_login_count >= warning:
            return _Condition(
                alert_type="security_elevated",
                severity="warning",
                threshold_percent=warning,
                message=(
                    f"{failed_login_count} failed login attempts in the last {window} minutes - "
                    f"above the warning threshold ({warning:.0f})"
                ),
            )
        return None

    def _evaluate_platform_metrics(self) -> tuple[int, int, int]:
        """API Latency / Error Rate (Phase 23): real HTTP server metrics
        queried from this platform's own Prometheus instance (see
        app/integrations/prometheus_client.py) - platform-wide, not
        deployment-scoped, since an HTTP request path has no single
        deployment owner the way CPU/memory/disk/network do. These are
        this platform's first fully unscoped alerts (deployment_id,
        project_id, and user_id all null)."""
        conditions: list[_Condition] = []
        latency_ms = average_latency_ms()
        if latency_ms is not None:
            condition = self._api_latency_condition(latency_ms)
            if condition is not None:
                conditions.append(condition)

        error_rate = error_rate_percent()
        if error_rate is not None:
            condition = self._error_rate_condition(error_rate)
            if condition is not None:
                conditions.append(condition)

        desired_types = {c.alert_type for c in conditions}
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        alerts_created = 0
        alerts_resolved = 0
        notifications_sent = 0

        for existing in self.repository.list_active_platform_wide():
            if (
                existing.alert_type.startswith(("api_latency_", "error_rate_"))
                and existing.alert_type not in desired_types
            ):
                existing.status = "resolved"
                existing.resolved_at = now
                alerts_resolved += 1

        for condition in conditions:
            if self.repository.get_active_platform_wide(condition.alert_type) is not None:
                continue  # already alerting at this tier - no-op
            alert = Alert(
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

    def _api_latency_condition(self, latency_ms: float) -> _Condition | None:
        warning = self.settings.ALERT_API_LATENCY_WARNING_THRESHOLD_MS
        critical = self.settings.ALERT_API_LATENCY_CRITICAL_THRESHOLD_MS
        saturated = self.settings.ALERT_API_LATENCY_SATURATED_THRESHOLD_MS

        if latency_ms >= saturated:
            return _Condition(
                alert_type="api_latency_saturated", severity="critical", threshold_percent=saturated,
                message=f"Average API latency is {latency_ms:.0f}ms - at or above the saturated threshold ({saturated:.0f}ms)",
            )
        if latency_ms >= critical:
            return _Condition(
                alert_type="api_latency_high", severity="critical", threshold_percent=critical,
                message=f"Average API latency is {latency_ms:.0f}ms - above the critical threshold ({critical:.0f}ms)",
            )
        if latency_ms >= warning:
            return _Condition(
                alert_type="api_latency_elevated", severity="warning", threshold_percent=warning,
                message=f"Average API latency is {latency_ms:.0f}ms - above the warning threshold ({warning:.0f}ms)",
            )
        return None

    def _error_rate_condition(self, error_rate_pct: float) -> _Condition | None:
        warning = self.settings.ALERT_ERROR_RATE_WARNING_THRESHOLD
        critical = self.settings.ALERT_ERROR_RATE_CRITICAL_THRESHOLD
        saturated = self.settings.ALERT_ERROR_RATE_SATURATED_THRESHOLD

        if error_rate_pct >= saturated:
            return _Condition(
                alert_type="error_rate_saturated", severity="critical", threshold_percent=saturated,
                message=f"API error rate is {error_rate_pct:.1f}% - at or above the saturated threshold ({saturated:.1f}%)",
            )
        if error_rate_pct >= critical:
            return _Condition(
                alert_type="error_rate_high", severity="critical", threshold_percent=critical,
                message=f"API error rate is {error_rate_pct:.1f}% - above the critical threshold ({critical:.1f}%)",
            )
        if error_rate_pct >= warning:
            return _Condition(
                alert_type="error_rate_elevated", severity="warning", threshold_percent=warning,
                message=f"API error rate is {error_rate_pct:.1f}% - above the warning threshold ({warning:.1f}%)",
            )
        return None

    def _evaluate_kubernetes(self) -> tuple[int, int, int]:
        """Node Failure / Container Failure (Phase 23): real cluster state
        read from the Kubernetes API (see
        app/integrations/kubernetes_monitor.py). `None` from either
        lookup (monitoring disabled, or the cluster/namespace is
        unreachable) means "skip entirely" - never treated as "healthy".
        Platform-wide, like API Latency/Error Rate above: a node or
        container failure has no single deployment/project/user owner in
        this platform's own data model. Pure state detection, not
        tiered - severity is always "critical" when anything unhealthy
        is found."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        alerts_created = 0
        alerts_resolved = 0
        notifications_sent = 0

        unhealthy_nodes = list_unhealthy_nodes()
        if unhealthy_nodes is not None:
            created, resolved, notified = self._sync_platform_state_alert(
                "node_failure",
                unhealthy_nodes,
                lambda items: f"{len(items)} node(s) unhealthy: "
                + ", ".join(f"{n.name} ({n.reason})" for n in items),
                now,
            )
            alerts_created += created
            alerts_resolved += resolved
            notifications_sent += notified

        unhealthy_containers = list_unhealthy_containers()
        if unhealthy_containers is not None:
            created, resolved, notified = self._sync_platform_state_alert(
                "container_failure",
                unhealthy_containers,
                lambda items: f"{len(items)} container(s) unhealthy: "
                + ", ".join(f"{c.pod_name}/{c.container_name} ({c.reason})" for c in items),
                now,
            )
            alerts_created += created
            alerts_resolved += resolved
            notifications_sent += notified

        return alerts_created, alerts_resolved, notifications_sent

    def _sync_platform_state_alert(self, alert_type, items, describe, now) -> tuple[int, int, int]:
        """Shared on/off (no-tier) idempotent create/resolve for a single
        platform-wide alert_type, driven by whether `items` is
        non-empty - the Node Failure/Container Failure equivalent of
        this service's other idempotent create/resolve loops."""
        existing = self.repository.get_active_platform_wide(alert_type)
        if not items:
            if existing is not None:
                existing.status = "resolved"
                existing.resolved_at = now
                self.db.commit()
                return 0, 1, 0
            return 0, 0, 0

        if existing is not None:
            return 0, 0, 0  # already alerting - no-op

        alert = Alert(
            alert_type=alert_type,
            severity="critical",
            threshold_percent=None,
            message=describe(items),
            status="active",
            triggered_at=now,
        )
        self.db.add(alert)
        self.db.flush()
        notifications_sent = dispatch(self.db, alert)
        self.db.commit()
        return 1, 0, notifications_sent

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

            storage_condition = self._limit_based_condition(
                "disk",
                "Storage",
                latest_usage.disk_usage_mb,
                deployment.disk_limit_mb,
                threshold_override,
                alert_type_prefix="storage",
            )
            if storage_condition is not None:
                conditions.append(storage_condition)

            cloud_usage_condition = self._cloud_usage_condition(latest_usage, deployment, threshold_override)
            if cloud_usage_condition is not None:
                conditions.append(cloud_usage_condition)

        pod_restart_condition = self._pod_restart_condition(deployment_id, threshold_override)
        if pod_restart_condition is not None:
            conditions.append(pod_restart_condition)

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
        alert_type_prefix: str | None = None,
    ) -> _Condition | None:
        """Shared 3-tier evaluation for any usage-vs-configured-limit metric
        (memory, disk, network - Phase 20/21) - skipped entirely when no
        limit is configured, since the raw usage value alone can't be
        turned into a utilization percentage without one to divide by (the
        same guard OptimizationService's memory recommendations already
        use). `metric` must match the lowercase prefix of both the
        ALERT_<METRIC>_*_THRESHOLD settings and the CloudAccountAlertThreshold
        override column names, e.g. "memory" -> ALERT_MEMORY_WARNING_THRESHOLD
        / memory_warning_threshold. `alert_type_prefix` (Phase 23) lets a
        second alert category reuse the same underlying metric/thresholds
        under its own alert_type name - see the "storage" call site, which
        reuses disk_usage_mb/disk_limit_mb (this platform collects no
        distinct filesystem/volume metric) but must still produce
        "storage_*" alert types, not "disk_*"."""
        if not limit_value or limit_value <= 0:
            return None
        percent = (usage_value / limit_value) * 100
        prefix = alert_type_prefix or metric

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
                alert_type=f"{prefix}_saturated",
                severity="critical",
                threshold_percent=saturated,
                message=f"{label} usage at {percent:.1f}% of the configured limit - at capacity",
            )
        if percent >= critical:
            return _Condition(
                alert_type=f"{prefix}_high",
                severity="critical",
                threshold_percent=critical,
                message=f"{label} usage at {percent:.1f}% of the configured limit - above critical threshold",
            )
        if percent >= warning:
            return _Condition(
                alert_type=f"{prefix}_elevated",
                severity="warning",
                threshold_percent=warning,
                message=f"{label} usage at {percent:.1f}% of the configured limit - above warning threshold",
            )
        return None

    def _cloud_usage_condition(
        self, usage: ResourceUsage, deployment: Deployment, override: CloudAccountAlertThreshold | None
    ) -> _Condition | None:
        """Cloud Usage (Phase 23): the highest utilization percentage across
        whichever of CPU/memory/disk/network are actually computable for
        this deployment right now - a single aggregate "how hot is this
        deployment overall" signal built entirely from data already
        collected for the other real evaluators, not a new metric source.

        Requires at least one of memory/disk/network to be configured -
        with none of those, this would just be a pure duplicate of the CPU
        alert (same value, same tiers most of the time), which is a
        meaningless "aggregate" of one input, not skipped for any other
        reason."""
        candidates = [usage.cpu_usage_percent]
        has_extra_dimension = False
        if deployment.memory_limit_mb:
            candidates.append((usage.memory_usage_mb / deployment.memory_limit_mb) * 100)
            has_extra_dimension = True
        if deployment.disk_limit_mb:
            candidates.append((usage.disk_usage_mb / deployment.disk_limit_mb) * 100)
            has_extra_dimension = True
        if deployment.network_limit_kbps:
            candidates.append(
                ((usage.network_in_kbps + usage.network_out_kbps) / deployment.network_limit_kbps) * 100
            )
            has_extra_dimension = True
        if not has_extra_dimension:
            return None
        percent = max(candidates)

        warning = self._threshold(
            override, "cloud_usage_warning_threshold", self.settings.ALERT_CLOUD_USAGE_WARNING_THRESHOLD
        )
        critical = self._threshold(
            override, "cloud_usage_critical_threshold", self.settings.ALERT_CLOUD_USAGE_CRITICAL_THRESHOLD
        )
        saturated = self._threshold(
            override, "cloud_usage_saturated_threshold", self.settings.ALERT_CLOUD_USAGE_SATURATED_THRESHOLD
        )

        label = "Cloud usage (highest of CPU/memory/disk/network)"
        if percent >= saturated:
            return _Condition(
                alert_type="cloud_usage_saturated",
                severity="critical",
                threshold_percent=saturated,
                message=f"{label} at {percent:.1f}% - at capacity",
            )
        if percent >= critical:
            return _Condition(
                alert_type="cloud_usage_high",
                severity="critical",
                threshold_percent=critical,
                message=f"{label} at {percent:.1f}% - above critical threshold",
            )
        if percent >= warning:
            return _Condition(
                alert_type="cloud_usage_elevated",
                severity="warning",
                threshold_percent=warning,
                message=f"{label} at {percent:.1f}% - above warning threshold",
            )
        return None

    def _pod_restart_condition(
        self, deployment_id: int, override: CloudAccountAlertThreshold | None
    ) -> _Condition | None:
        """Pod Restart (Phase 23): the highest Pod.restart_count across this
        deployment's real, already-collected Pod rows (see POST
        /deployments/{id}/pods, Phase 2) - restart_count was tracked from
        the start but never alerted on until now. Skipped when the
        deployment has no pods recorded at all, since there is nothing
        real to evaluate; a raw count, not a percent, so thresholds are
        absolute restart counts (default 3/5/10), not 0-100 bounded."""
        max_restart_count = self.db.scalar(
            select(func.max(Pod.restart_count)).where(Pod.deployment_id == deployment_id)
        )
        if max_restart_count is None:
            return None

        warning = self._threshold(
            override, "pod_restart_warning_threshold", self.settings.ALERT_POD_RESTART_WARNING_THRESHOLD
        )
        critical = self._threshold(
            override, "pod_restart_critical_threshold", self.settings.ALERT_POD_RESTART_CRITICAL_THRESHOLD
        )
        saturated = self._threshold(
            override, "pod_restart_saturated_threshold", self.settings.ALERT_POD_RESTART_SATURATED_THRESHOLD
        )

        if max_restart_count >= saturated:
            return _Condition(
                alert_type="pod_restart_saturated",
                severity="critical",
                threshold_percent=saturated,
                message=f"A pod has restarted {max_restart_count} times - at or above the saturated threshold ({saturated:.0f})",
            )
        if max_restart_count >= critical:
            return _Condition(
                alert_type="pod_restart_high",
                severity="critical",
                threshold_percent=critical,
                message=f"A pod has restarted {max_restart_count} times - above the critical threshold ({critical:.0f})",
            )
        if max_restart_count >= warning:
            return _Condition(
                alert_type="pod_restart_elevated",
                severity="warning",
                threshold_percent=warning,
                message=f"A pod has restarted {max_restart_count} times - above the warning threshold ({warning:.0f})",
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
