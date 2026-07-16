"""Data-access layer for the Role entity."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import Role
from app.repositories.base_repository import BaseRepository


class RoleRepository(BaseRepository[Role]):
    def __init__(self, db: Session):
        super().__init__(db, Role)

    def get_by_name(self, name: str) -> Role | None:
        stmt = select(Role).where(Role.name == name)
        return self.db.scalars(stmt).first()

    def get_or_create(self, name: str, description: str | None = None) -> Role:
        role = self.get_by_name(name)
        if role is not None:
            return role
        role = Role(name=name, description=description)
        return self.create(role)
