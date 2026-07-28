"""Data-access layer for the Alert entity."""
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from app.models.alert import Alert
from app.models.deployment import Deployment
from app.models.microservice import Microservice
from app.models.project import Project
from app.repositories.base_repository import BaseRepository


class AlertRepository(BaseRepository[Alert]):
    def __init__(self, db: Session):
        super().__init__(db, Alert)

    def get_active(self, deployment_id: int, alert_type: str) -> Alert | None:
        stmt = select(Alert).where(
            Alert.deployment_id == deployment_id,
            Alert.alert_type == alert_type,
            Alert.status == "active",
        )
        return self.db.scalars(stmt).first()

    def list_active_for_deployment(self, deployment_id: int) -> list[Alert]:
        stmt = select(Alert).where(
            Alert.deployment_id == deployment_id, Alert.status == "active"
        )
        return list(self.db.scalars(stmt).all())

    def get_active_for_project(self, project_id: int, alert_type: str) -> Alert | None:
        stmt = select(Alert).where(
            Alert.project_id == project_id,
            Alert.alert_type == alert_type,
            Alert.status == "active",
        )
        return self.db.scalars(stmt).first()

    def list_active_for_project(self, project_id: int) -> list[Alert]:
        stmt = select(Alert).where(Alert.project_id == project_id, Alert.status == "active")
        return list(self.db.scalars(stmt).all())

    def get_active_platform_wide(self, alert_type: str) -> Alert | None:
        """For alert types with no deployment/project/user scope at all
        (Phase 23 - API Latency/Error Rate, real HTTP server metrics with
        no single owning entity)."""
        stmt = select(Alert).where(
            Alert.deployment_id.is_(None),
            Alert.project_id.is_(None),
            Alert.user_id.is_(None),
            Alert.alert_type == alert_type,
            Alert.status == "active",
        )
        return self.db.scalars(stmt).first()

    def list_active_platform_wide(self) -> list[Alert]:
        stmt = select(Alert).where(
            Alert.deployment_id.is_(None),
            Alert.project_id.is_(None),
            Alert.user_id.is_(None),
            Alert.status == "active",
        )
        return list(self.db.scalars(stmt).all())

    def get_active_for_user(self, user_id: int, alert_type: str) -> Alert | None:
        stmt = select(Alert).where(
            Alert.user_id == user_id,
            Alert.alert_type == alert_type,
            Alert.status == "active",
        )
        return self.db.scalars(stmt).first()

    def list_active_for_user(self, user_id: int) -> list[Alert]:
        stmt = select(Alert).where(Alert.user_id == user_id, Alert.status == "active")
        return list(self.db.scalars(stmt).all())

    def list_active_for_deployments(self, deployment_ids: list[int]) -> list[Alert]:
        """Every active alert across a set of deployments in one query -
        used to show a cloud provider account's alerts as a single list
        (see CloudProviderAccountService.list_active_alerts), rather than
        one query per linked deployment."""
        if not deployment_ids:
            return []
        stmt = (
            select(Alert)
            .where(Alert.deployment_id.in_(deployment_ids), Alert.status == "active")
            .order_by(Alert.triggered_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def search(
        self,
        deployment_id: int | None,
        status: str | None,
        severity: str | None,
        offset: int,
        limit: int,
        owner_id: int | None = None,
    ) -> tuple[list[Alert], int]:
        """deployment_id=None searches across all deployments (the global
        `GET /alerts` listing); a specific ID scopes to one deployment.

        owner_id (Phase 24) restricts the global listing to one user's own
        alerts - None means no owner filter (only a platform is_superuser
        calls it that way; every other caller passes their own
        current_user.id - see AlertService.list_global). An alert matches
        an owner via whichever of its three mutually-exclusive scopes it
        actually has: deployment_id (via the deployment's project owner),
        project_id (via that project's own owner), or user_id (directly) -
        genuinely platform-wide alerts (all three null) never match any
        owner_id and are excluded entirely for non-superusers.
        """
        stmt = select(Alert)
        count_stmt = select(func.count()).select_from(Alert)

        if deployment_id is not None:
            condition = Alert.deployment_id == deployment_id
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if status:
            condition = Alert.status == status
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if severity:
            condition = Alert.severity == severity
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if owner_id is not None:
            deployment_project = aliased(Project)
            cost_project = aliased(Project)
            owner_condition = or_(
                deployment_project.owner_id == owner_id,
                cost_project.owner_id == owner_id,
                Alert.user_id == owner_id,
            )
            stmt = (
                stmt.outerjoin(Deployment, Deployment.id == Alert.deployment_id)
                .outerjoin(Microservice, Microservice.id == Deployment.microservice_id)
                .outerjoin(deployment_project, deployment_project.id == Microservice.project_id)
                .outerjoin(cost_project, cost_project.id == Alert.project_id)
                .where(owner_condition)
            )
            count_stmt = (
                count_stmt.outerjoin(Deployment, Deployment.id == Alert.deployment_id)
                .outerjoin(Microservice, Microservice.id == Deployment.microservice_id)
                .outerjoin(deployment_project, deployment_project.id == Microservice.project_id)
                .outerjoin(cost_project, cost_project.id == Alert.project_id)
                .where(owner_condition)
            )

        stmt = stmt.order_by(Alert.triggered_at.desc()).offset(offset).limit(limit)

        items = list(self.db.scalars(stmt).all())
        total = self.db.scalar(count_stmt) or 0
        return items, total
