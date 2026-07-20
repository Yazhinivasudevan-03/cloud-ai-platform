"""Data-access layer for the Deployment entity."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.deployment import Deployment
from app.repositories.base_repository import BaseRepository

_SORT_COLUMNS = {
    "name": Deployment.name,
    "created_at": Deployment.created_at,
    "status": Deployment.status,
}


class DeploymentRepository(BaseRepository[Deployment]):
    def __init__(self, db: Session):
        super().__init__(db, Deployment)

    def get_by_microservice_identity(
        self, microservice_id: int, name: str, namespace: str
    ) -> Deployment | None:
        stmt = select(Deployment).where(
            Deployment.microservice_id == microservice_id,
            Deployment.name == name,
            Deployment.namespace == namespace,
        )
        return self.db.scalars(stmt).first()

    def list_cloud_linked(self) -> list[Deployment]:
        """Every deployment with a cloud provider account + resource
        identifier configured - i.e. eligible for real-time cloud metric
        syncing (see CloudSyncService)."""
        stmt = select(Deployment).where(
            Deployment.cloud_provider_account_id.is_not(None),
            Deployment.cloud_resource_identifier.is_not(None),
        )
        return list(self.db.scalars(stmt).all())

    def list_by_cloud_account(self, cloud_provider_account_id: int) -> list[Deployment]:
        """Every deployment linked to one specific cloud provider account -
        used by the consolidated "at a glance" usage view on the Cloud
        Accounts page (see CloudProviderAccountService.list_linked_deployments)."""
        stmt = select(Deployment).where(
            Deployment.cloud_provider_account_id == cloud_provider_account_id
        )
        return list(self.db.scalars(stmt).all())

    def search(
        self,
        microservice_id: int,
        status: str | None,
        namespace: str | None,
        sort_by: str,
        order: str,
        offset: int,
        limit: int,
    ) -> tuple[list[Deployment], int]:
        stmt = select(Deployment).where(Deployment.microservice_id == microservice_id)
        count_stmt = (
            select(func.count())
            .select_from(Deployment)
            .where(Deployment.microservice_id == microservice_id)
        )

        if status:
            condition = Deployment.status == status
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if namespace:
            condition = Deployment.namespace == namespace
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        sort_column = _SORT_COLUMNS.get(sort_by, Deployment.created_at)
        stmt = stmt.order_by(sort_column.desc() if order == "desc" else sort_column.asc())
        stmt = stmt.offset(offset).limit(limit)

        items = list(self.db.scalars(stmt).all())
        total = self.db.scalar(count_stmt) or 0
        return items, total
