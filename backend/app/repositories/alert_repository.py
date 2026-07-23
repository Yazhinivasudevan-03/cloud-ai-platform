"""Data-access layer for the Alert entity."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.alert import Alert
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
    ) -> tuple[list[Alert], int]:
        """deployment_id=None searches across all deployments (the global
        `GET /alerts` listing); a specific ID scopes to one deployment."""
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

        stmt = stmt.order_by(Alert.triggered_at.desc()).offset(offset).limit(limit)

        items = list(self.db.scalars(stmt).all())
        total = self.db.scalar(count_stmt) or 0
        return items, total
