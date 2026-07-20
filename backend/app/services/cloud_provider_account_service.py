"""Business logic for a user's own cloud provider accounts (self-service
only, same ownership pattern as NotificationService). No limit is enforced
anywhere in this layer on how many accounts a single user may register."""
from sqlalchemy.orm import Session

from app.models.cloud_provider_account import CloudProviderAccount
from app.models.deployment import Deployment
from app.models.resource_usage import ResourceUsage
from app.repositories.cloud_provider_account_repository import CloudProviderAccountRepository
from app.repositories.deployment_repository import DeploymentRepository
from app.repositories.resource_usage_repository import ResourceUsageRepository
from app.schemas.cloud_provider_account import CloudProviderAccountCreate, CloudProviderAccountUpdate
from app.utils.crypto import encrypt_credentials
from app.utils.exceptions import ConflictError, ForbiddenError, NotFoundError


class CloudProviderAccountService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = CloudProviderAccountRepository(db)
        self.deployment_repository = DeploymentRepository(db)
        self.resource_usage_repository = ResourceUsageRepository(db)

    def create(self, user_id: int, payload: CloudProviderAccountCreate) -> CloudProviderAccount:
        if self.repository.get_by_user_and_name(user_id, payload.account_name) is not None:
            raise ConflictError(
                f"You already have a cloud account named '{payload.account_name}'",
                code="CLOUD_ACCOUNT_NAME_EXISTS",
            )

        account = CloudProviderAccount(
            user_id=user_id,
            provider=payload.provider,
            account_name=payload.account_name,
            region=payload.region,
            account_identifier=payload.account_identifier,
            credentials_encrypted=encrypt_credentials(payload.credentials),
        )
        return self.repository.create(account)

    def list_for_user(
        self, user_id: int, provider: str | None, page: int, page_size: int
    ) -> tuple[list[CloudProviderAccount], int]:
        offset = (page - 1) * page_size
        return self.repository.search(user_id, provider, offset, page_size)

    def get_own(self, account_id: int, current_user_id: int) -> CloudProviderAccount:
        account = self._get_owned_or_raise(account_id, current_user_id)
        return account

    def update(
        self, account_id: int, current_user_id: int, payload: CloudProviderAccountUpdate
    ) -> CloudProviderAccount:
        account = self._get_owned_or_raise(account_id, current_user_id)

        if payload.account_name is not None and payload.account_name != account.account_name:
            existing = self.repository.get_by_user_and_name(current_user_id, payload.account_name)
            if existing is not None and existing.id != account.id:
                raise ConflictError(
                    f"You already have a cloud account named '{payload.account_name}'",
                    code="CLOUD_ACCOUNT_NAME_EXISTS",
                )
            account.account_name = payload.account_name

        if payload.provider is not None:
            account.provider = payload.provider
        if payload.region is not None:
            account.region = payload.region
        if payload.account_identifier is not None:
            account.account_identifier = payload.account_identifier
        if payload.is_active is not None:
            account.is_active = payload.is_active
        if payload.credentials is not None:
            account.credentials_encrypted = encrypt_credentials(payload.credentials)

        self.db.commit()
        self.db.refresh(account)
        return account

    def delete(self, account_id: int, current_user_id: int) -> None:
        account = self._get_owned_or_raise(account_id, current_user_id)
        self.repository.delete(account)

    def list_linked_deployments(
        self, account_id: int, current_user_id: int
    ) -> list[tuple[Deployment, ResourceUsage | None]]:
        """Every deployment linked to this account, each paired with its
        most recent resource usage row (or None if never synced/recorded) -
        the "at a glance" consolidated usage view."""
        account = self._get_owned_or_raise(account_id, current_user_id)
        deployments = self.deployment_repository.list_by_cloud_account(account.id)
        return [
            (deployment, self.resource_usage_repository.get_latest_for_deployment(deployment.id))
            for deployment in deployments
        ]

    def _get_owned_or_raise(self, account_id: int, current_user_id: int) -> CloudProviderAccount:
        account = self.repository.get_by_id(account_id)
        if account is None:
            raise NotFoundError(
                f"Cloud provider account {account_id} not found", code="CLOUD_ACCOUNT_NOT_FOUND"
            )
        if account.user_id != current_user_id:
            raise ForbiddenError(
                "Cannot access another user's cloud provider account", code="NOT_YOUR_CLOUD_ACCOUNT"
            )
        return account
