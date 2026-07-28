"""Business logic for reading and updating Alert lifecycle state."""
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.user import User
from app.repositories.alert_repository import AlertRepository
from app.repositories.deployment_repository import DeploymentRepository
from app.schemas.alert import AlertStatus
from app.utils.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.utils.ownership import raise_if_cannot_access_project


class AlertService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AlertRepository(db)
        self.deployment_repository = DeploymentRepository(db)

    def _raise_if_cannot_access_alert(self, alert: Alert, current_user: User) -> None:
        """Alert has three mutually-exclusive scopes (deployment/project/
        user - see app/models/alert.py), plus a fourth case: genuinely
        platform-wide alerts (API Latency/Error Rate/Node Failure/
        Container Failure - all three FK fields null), viewable only by a
        platform is_superuser."""
        if current_user.is_superuser:
            return
        if alert.deployment_id is not None:
            raise_if_cannot_access_project(alert.deployment.microservice.project, current_user)
        elif alert.project_id is not None:
            raise_if_cannot_access_project(alert.project, current_user)
        elif alert.user_id is not None:
            if alert.user_id != current_user.id:
                raise ForbiddenError("Cannot access another user's alert", code="NOT_YOUR_ALERT")
        else:
            raise ForbiddenError("Cannot access a platform-wide alert", code="NOT_YOUR_ALERT")

    def get(self, alert_id: int, current_user: User) -> Alert:
        alert = self.repository.get_by_id(alert_id)
        if alert is None:
            raise NotFoundError(f"Alert {alert_id} not found", code="ALERT_NOT_FOUND")
        self._raise_if_cannot_access_alert(alert, current_user)
        return alert

    def list_for_deployment(
        self,
        deployment_id: int,
        status: str | None,
        severity: str | None,
        page: int,
        page_size: int,
        current_user: User,
    ) -> tuple[list[Alert], int]:
        deployment = self.deployment_repository.get_by_id(deployment_id)
        if deployment is None:
            raise NotFoundError(
                f"Deployment {deployment_id} not found", code="DEPLOYMENT_NOT_FOUND"
            )
        raise_if_cannot_access_project(deployment.microservice.project, current_user)
        offset = (page - 1) * page_size
        return self.repository.search(deployment_id, status, severity, offset, page_size)

    def list_global(
        self,
        deployment_id: int | None,
        status: str | None,
        severity: str | None,
        page: int,
        page_size: int,
        current_user: User,
    ) -> tuple[list[Alert], int]:
        """Cross-deployment listing for dashboard-level views (e.g. a
        platform-wide Alerts page) - `deployment_id` is an optional filter
        here, not a required scope. Phase 24: scoped to the current user's
        own alerts unless they're a platform is_superuser (owner_id=None
        -> no filter - see AlertRepository.search)."""
        if deployment_id is not None:
            deployment = self.deployment_repository.get_by_id(deployment_id)
            if deployment is None:
                raise NotFoundError(
                    f"Deployment {deployment_id} not found", code="DEPLOYMENT_NOT_FOUND"
                )
            raise_if_cannot_access_project(deployment.microservice.project, current_user)
        offset = (page - 1) * page_size
        owner_id = None if current_user.is_superuser else current_user.id
        return self.repository.search(deployment_id, status, severity, offset, page_size, owner_id)

    def update_status(self, alert_id: int, new_status: AlertStatus, current_user: User) -> Alert:
        alert = self.get(alert_id, current_user)
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
