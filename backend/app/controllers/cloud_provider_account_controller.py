"""Controller layer for a user's own CloudProviderAccount endpoints."""
import math

from sqlalchemy.orm import Session

from app.schemas.cloud_provider_account import (
    CloudProviderAccountCreate,
    CloudProviderAccountRead,
    CloudProviderAccountUpdate,
)
from app.schemas.common import PaginatedResponse, PaginationMeta
from app.services.cloud_provider_account_service import CloudProviderAccountService


class CloudProviderAccountController:
    def __init__(self, db: Session):
        self.service = CloudProviderAccountService(db)

    def create(self, user_id: int, payload: CloudProviderAccountCreate) -> CloudProviderAccountRead:
        return CloudProviderAccountRead.model_validate(self.service.create(user_id, payload))

    def list_for_user(
        self, user_id: int, provider: str | None, page: int, page_size: int
    ) -> PaginatedResponse[CloudProviderAccountRead]:
        items, total = self.service.list_for_user(user_id, provider, page, page_size)
        total_pages = math.ceil(total / page_size) if page_size else 0
        return PaginatedResponse[CloudProviderAccountRead](
            items=[CloudProviderAccountRead.model_validate(i) for i in items],
            meta=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=total_pages
            ),
        )

    def get_own(self, account_id: int, current_user_id: int) -> CloudProviderAccountRead:
        return CloudProviderAccountRead.model_validate(
            self.service.get_own(account_id, current_user_id)
        )

    def update(
        self, account_id: int, current_user_id: int, payload: CloudProviderAccountUpdate
    ) -> CloudProviderAccountRead:
        return CloudProviderAccountRead.model_validate(
            self.service.update(account_id, current_user_id, payload)
        )

    def delete(self, account_id: int, current_user_id: int) -> None:
        self.service.delete(account_id, current_user_id)
