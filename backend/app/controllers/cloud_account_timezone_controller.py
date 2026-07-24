"""Controller layer for the per-cloud-account timezone endpoints."""
from sqlalchemy.orm import Session

from app.schemas.cloud_account_timezone import (
    CloudAccountTimezoneCreate,
    CloudAccountTimezoneRead,
    CloudAccountTimezoneUpdate,
)
from app.services.cloud_account_timezone_service import CloudAccountTimezoneService


class CloudAccountTimezoneController:
    def __init__(self, db: Session):
        self.service = CloudAccountTimezoneService(db)

    def list_for_account(self, account_id: int, current_user_id: int) -> list[CloudAccountTimezoneRead]:
        return self.service.list_for_account(account_id, current_user_id)

    def create(
        self, account_id: int, current_user_id: int, payload: CloudAccountTimezoneCreate
    ) -> CloudAccountTimezoneRead:
        return self.service.create(account_id, current_user_id, payload)

    def update(
        self, account_id: int, timezone_id: int, current_user_id: int, payload: CloudAccountTimezoneUpdate
    ) -> CloudAccountTimezoneRead:
        return self.service.update(account_id, timezone_id, current_user_id, payload)

    def delete(self, account_id: int, timezone_id: int, current_user_id: int) -> None:
        self.service.delete(account_id, timezone_id, current_user_id)
