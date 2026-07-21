"""Controller layer for a user's own CloudProviderAccount endpoints."""
import math

from sqlalchemy.orm import Session

from app.schemas.alert import AlertRead
from app.schemas.cloud_provider_account import (
    CloudAccountDeploymentSummary,
    CloudProviderAccountCreate,
    CloudProviderAccountRead,
    CloudProviderAccountUpdate,
)
from app.schemas.common import PaginatedResponse, PaginationMeta
from app.schemas.resource_usage import ResourceUsageRead
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

    def list_linked_deployments(
        self, account_id: int, current_user_id: int
    ) -> list[CloudAccountDeploymentSummary]:
        pairs = self.service.list_linked_deployments(account_id, current_user_id)
        return [
            CloudAccountDeploymentSummary(
                deployment_id=deployment.id,
                deployment_name=deployment.name,
                namespace=deployment.namespace,
                cloud_resource_identifier=deployment.cloud_resource_identifier,
                latest_usage=ResourceUsageRead.model_validate(usage) if usage else None,
            )
            for deployment, usage in pairs
        ]

    def list_active_alerts(self, account_id: int, current_user_id: int) -> list[AlertRead]:
        alerts = self.service.list_active_alerts(account_id, current_user_id)
        return [AlertRead.model_validate(a) for a in alerts]
