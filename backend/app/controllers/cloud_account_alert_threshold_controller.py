"""Controller layer for per-cloud-account alert threshold endpoints."""
from sqlalchemy.orm import Session

from app.schemas.cloud_account_alert_threshold import (
    CloudAccountAlertThresholdRead,
    CloudAccountAlertThresholdUpdate,
)
from app.services.cloud_account_alert_threshold_service import CloudAccountAlertThresholdService


class CloudAccountAlertThresholdController:
    def __init__(self, db: Session):
        self.service = CloudAccountAlertThresholdService(db)

    def get(self, account_id: int, current_user_id: int) -> CloudAccountAlertThresholdRead:
        return self.service.get(account_id, current_user_id)

    def update(
        self, account_id: int, current_user_id: int, payload: CloudAccountAlertThresholdUpdate
    ) -> CloudAccountAlertThresholdRead:
        return self.service.update(account_id, current_user_id, payload)
