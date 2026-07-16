"""Business logic for reading and updating Alert lifecycle state."""
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.repositories.alert_repository import AlertRepository
from app.repositories.deployment_repository import DeploymentRepository
from app.schemas.alert import AlertStatus
from app.utils.exceptions import ConflictError, NotFoundError


class AlertService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AlertRepository(db)
        self.deployment_repository = DeploymentRepository(db)

    def get(self, alert_id: int) -> Alert:
        alert = self.repository.get_by_id(alert_id)
        if alert is None:
            raise NotFoundError(f"Alert {alert_id} not found", code="ALERT_NOT_FOUND")
        return alert

    def list_for_deployment(
        self, deployment_id: int, status: str | None, severity: str | None, page: int, page_size: int
    ) -> tuple[list[Alert], int]:
        if self.deployment_repository.get_by_id(deployment_id) is None:
            raise NotFoundError(
                f"Deployment {deployment_id} not found", code="DEPLOYMENT_NOT_FOUND"
            )
        offset = (page - 1) * page_size
        return self.repository.search(deployment_id, status, severity, offset, page_size)

    def list_global(
        self,
        deployment_id: int | None,
        status: str | None,
        severity: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Alert], int]:
        """Cross-deployment listing for dashboard-level views (e.g. a
        platform-wide Alerts page) - `deployment_id` is an optional filter
        here, not a required scope."""
        if deployment_id is not None and self.deployment_repository.get_by_id(deployment_id) is None:
            raise NotFoundError(
                f"Deployment {deployment_id} not found", code="DEPLOYMENT_NOT_FOUND"
            )
        offset = (page - 1) * page_size
        return self.repository.search(deployment_id, status, severity, offset, page_size)

    def update_status(self, alert_id: int, new_status: AlertStatus) -> Alert:
        alert = self.get(alert_id)
        valid_transitions = {
            "active": {"acknowledged", "resolved"},
            "acknowledged": {"resolved"},
        }
        allowed = valid_transitions.get(alert.status, set())
        if new_status.value not in allowed:
            raise ConflictError(
                f"Cannot transition alert from '{alert.status}' to '{new_status.value}'",
                code="INVALID_ALERT_TRANSITION",
            )
        alert.status = new_status.value
        if new_status == AlertStatus.RESOLVED:
            from datetime import datetime, timezone

            alert.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.db.commit()
        self.db.refresh(alert)
        return alert
