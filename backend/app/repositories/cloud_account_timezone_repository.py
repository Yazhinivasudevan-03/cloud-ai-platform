"""Data-access layer for the CloudAccountTimezone entity."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cloud_account_timezone import CloudAccountTimezone
from app.repositories.base_repository import BaseRepository


class CloudAccountTimezoneRepository(BaseRepository[CloudAccountTimezone]):
    def __init__(self, db: Session):
        super().__init__(db, CloudAccountTimezone)

    def list_for_account(self, cloud_provider_account_id: int) -> list[CloudAccountTimezone]:
        stmt = (
            select(CloudAccountTimezone)
            .where(CloudAccountTimezone.cloud_provider_account_id == cloud_provider_account_id)
            .order_by(CloudAccountTimezone.created_at)
        )
        return list(self.db.scalars(stmt).all())
