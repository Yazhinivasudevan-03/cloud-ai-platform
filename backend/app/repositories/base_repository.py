"""Generic repository providing common CRUD operations for any SQLAlchemy model.

Concrete repositories subclass `BaseRepository[ModelType]` and add
entity-specific query methods on top of these generic operations, following
the Repository Pattern to keep data-access logic out of services/controllers.
"""
from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    def __init__(self, db: Session, model: type[ModelType]):
        self.db = db
        self.model = model

    def get_by_id(self, entity_id: int) -> ModelType | None:
        return self.db.get(self.model, entity_id)

    def list(self, offset: int = 0, limit: int = 20) -> list[ModelType]:
        stmt = select(self.model).offset(offset).limit(limit)
        return list(self.db.scalars(stmt).all())

    def count(self) -> int:
        stmt = select(func.count()).select_from(self.model)
        return self.db.scalar(stmt) or 0

    def create(self, entity: ModelType) -> ModelType:
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def delete(self, entity: ModelType) -> None:
        self.db.delete(entity)
        self.db.commit()
