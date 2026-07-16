"""Data-access layer for the Microservice entity."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.microservice import Microservice
from app.repositories.base_repository import BaseRepository

_SORT_COLUMNS = {"name": Microservice.name, "created_at": Microservice.created_at}


class MicroserviceRepository(BaseRepository[Microservice]):
    def __init__(self, db: Session):
        super().__init__(db, Microservice)

    def get_by_project_and_name(self, project_id: int, name: str) -> Microservice | None:
        stmt = select(Microservice).where(
            Microservice.project_id == project_id, Microservice.name == name
        )
        return self.db.scalars(stmt).first()

    def search(
        self,
        project_id: int,
        name_contains: str | None,
        language: str | None,
        sort_by: str,
        order: str,
        offset: int,
        limit: int,
    ) -> tuple[list[Microservice], int]:
        stmt = select(Microservice).where(Microservice.project_id == project_id)
        count_stmt = (
            select(func.count())
            .select_from(Microservice)
            .where(Microservice.project_id == project_id)
        )

        if name_contains:
            condition = Microservice.name.ilike(f"%{name_contains}%")
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if language:
            condition = Microservice.language == language
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        sort_column = _SORT_COLUMNS.get(sort_by, Microservice.created_at)
        stmt = stmt.order_by(sort_column.desc() if order == "desc" else sort_column.asc())
        stmt = stmt.offset(offset).limit(limit)

        items = list(self.db.scalars(stmt).all())
        total = self.db.scalar(count_stmt) or 0
        return items, total
