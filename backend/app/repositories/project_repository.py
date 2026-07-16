"""Data-access layer for the Project entity."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.project import Project
from app.repositories.base_repository import BaseRepository

_SORT_COLUMNS = {"name": Project.name, "created_at": Project.created_at}


class ProjectRepository(BaseRepository[Project]):
    def __init__(self, db: Session):
        super().__init__(db, Project)

    def get_by_name(self, name: str) -> Project | None:
        stmt = select(Project).where(Project.name == name)
        return self.db.scalars(stmt).first()

    def search(
        self,
        name_contains: str | None,
        sort_by: str,
        order: str,
        offset: int,
        limit: int,
    ) -> tuple[list[Project], int]:
        stmt = select(Project)
        count_stmt = select(func.count()).select_from(Project)

        if name_contains:
            condition = Project.name.ilike(f"%{name_contains}%")
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        sort_column = _SORT_COLUMNS.get(sort_by, Project.created_at)
        stmt = stmt.order_by(sort_column.desc() if order == "desc" else sort_column.asc())
        stmt = stmt.offset(offset).limit(limit)

        items = list(self.db.scalars(stmt).all())
        total = self.db.scalar(count_stmt) or 0
        return items, total
