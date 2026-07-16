"""Data-access layer for the Pod entity."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.pod import Pod
from app.repositories.base_repository import BaseRepository

_SORT_COLUMNS = {"pod_name": Pod.pod_name, "created_at": Pod.created_at}


class PodRepository(BaseRepository[Pod]):
    def __init__(self, db: Session):
        super().__init__(db, Pod)

    def get_by_deployment_and_name(self, deployment_id: int, pod_name: str) -> Pod | None:
        stmt = select(Pod).where(Pod.deployment_id == deployment_id, Pod.pod_name == pod_name)
        return self.db.scalars(stmt).first()

    def search(
        self,
        deployment_id: int,
        status: str | None,
        sort_by: str,
        order: str,
        offset: int,
        limit: int,
    ) -> tuple[list[Pod], int]:
        stmt = select(Pod).where(Pod.deployment_id == deployment_id)
        count_stmt = (
            select(func.count()).select_from(Pod).where(Pod.deployment_id == deployment_id)
        )

        if status:
            condition = Pod.status == status
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        sort_column = _SORT_COLUMNS.get(sort_by, Pod.created_at)
        stmt = stmt.order_by(sort_column.desc() if order == "desc" else sort_column.asc())
        stmt = stmt.offset(offset).limit(limit)

        items = list(self.db.scalars(stmt).all())
        total = self.db.scalar(count_stmt) or 0
        return items, total
