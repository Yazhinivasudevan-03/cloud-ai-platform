"""Data-access layer for the CloudAccountAlertThreshold entity (one row per
CloudProviderAccount)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cloud_account_alert_threshold import CloudAccountAlertThreshold
from app.repositories.base_repository import BaseRepository


class CloudAccountAlertThresholdRepository(BaseRepository[CloudAccountAlertThreshold]):
    def __init__(self, db: Session):
        super().__init__(db, CloudAccountAlertThreshold)

    def get_by_account_id(self, cloud_provider_account_id: int) -> CloudAccountAlertThreshold | None:
        stmt = select(CloudAccountAlertThreshold).where(
            CloudAccountAlertThreshold.cloud_provider_account_id == cloud_provider_account_id
        )
        return self.db.scalars(stmt).first()

    def get_or_create(self, cloud_provider_account_id: int) -> CloudAccountAlertThreshold:
        threshold = self.get_by_account_id(cloud_provider_account_id)
        if threshold is None:
            threshold = self.create(
                CloudAccountAlertThreshold(cloud_provider_account_id=cloud_provider_account_id)
            )
        return threshold
