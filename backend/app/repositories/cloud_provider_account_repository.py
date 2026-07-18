"""Data-access layer for the CloudProviderAccount entity."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cloud_provider_account import CloudProviderAccount
from app.repositories.base_repository import BaseRepository


class CloudProviderAccountRepository(BaseRepository[CloudProviderAccount]):
    def __init__(self, db: Session):
        super().__init__(db, CloudProviderAccount)

    def search(
        self, user_id: int, provider: str | None, offset: int, limit: int
    ) -> tuple[list[CloudProviderAccount], int]:
        stmt = select(CloudProviderAccount).where(CloudProviderAccount.user_id == user_id)
        count_stmt = (
            select(func.count())
            .select_from(CloudProviderAccount)
            .where(CloudProviderAccount.user_id == user_id)
        )

        if provider is not None:
            condition = CloudProviderAccount.provider == provider
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        stmt = stmt.order_by(CloudProviderAccount.created_at.desc()).offset(offset).limit(limit)

        items = list(self.db.scalars(stmt).all())
        total = self.db.scalar(count_stmt) or 0
        return items, total

    def get_by_user_and_name(self, user_id: int, account_name: str) -> CloudProviderAccount | None:
        stmt = select(CloudProviderAccount).where(
            CloudProviderAccount.user_id == user_id,
            CloudProviderAccount.account_name == account_name,
        )
        return self.db.scalars(stmt).first()
