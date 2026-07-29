"""Business logic for real cloud resource provisioning (Phase 25D) - the
first part of this platform capable of creating/destroying a user's actual
infrastructure if pointed at genuine (non-test) credentials. Every attempt,
successful or not, is recorded in the existing AuditLog (no new model -
that table is already a generic action/entity_type/entity_id/details
record, see app/models/audit_log.py), and every destroy requires the
caller to type the resource's own id back as confirmation - a mismatch is
a 422 validation failure, not a 403, since it isn't an authorization
question.
"""
import json

from sqlalchemy.orm import Session

from app.integrations.cloud_provider_client import CloudResourceSummary
from app.integrations.provider_factory import get_cloud_provider_client
from app.models.audit_log import AuditLog
from app.models.cloud_provider_account import CloudProviderAccount
from app.repositories.cloud_provider_account_repository import CloudProviderAccountRepository
from app.schemas.cloud_resource import PROVISIONABLE_RESOURCE_TYPES
from app.utils.crypto import decrypt_credentials
from app.utils.exceptions import AppException, ForbiddenError, NotFoundError, ValidationAppError


class CloudProvisioningService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = CloudProviderAccountRepository(db)

    def deploy(
        self, account_id: int, current_user_id: int, resource_type: str, region: str, spec: dict
    ) -> CloudResourceSummary:
        if resource_type not in PROVISIONABLE_RESOURCE_TYPES:
            raise ValidationAppError(
                f"'{resource_type}' is not a provisionable resource type - use one of "
                f"{', '.join(PROVISIONABLE_RESOURCE_TYPES)}",
                code="INVALID_PROVISIONABLE_RESOURCE_TYPE",
            )
        account = self._get_owned_or_raise(account_id, current_user_id)

        try:
            client = get_cloud_provider_client(
                account.provider, decrypt_credentials(account.credentials_encrypted), account.region
            )
            result = client.deploy(region, resource_type, spec)
        except AppException as exc:
            self._audit(current_user_id, "cloud_resource_deploy", resource_type, account, region, None, str(exc))
            raise

        self._audit(current_user_id, "cloud_resource_deploy", resource_type, account, region, result["id"], "success")
        return result

    def destroy(
        self,
        account_id: int,
        current_user_id: int,
        resource_type: str,
        resource_id: str,
        region: str,
        confirm: str,
    ) -> None:
        if resource_type not in PROVISIONABLE_RESOURCE_TYPES:
            raise ValidationAppError(
                f"'{resource_type}' is not a provisionable resource type - use one of "
                f"{', '.join(PROVISIONABLE_RESOURCE_TYPES)}",
                code="INVALID_PROVISIONABLE_RESOURCE_TYPE",
            )
        if confirm != resource_id:
            raise ValidationAppError(
                "The confirmation value must exactly match the resource's own id - this action "
                "cannot be undone",
                code="DESTROY_CONFIRMATION_MISMATCH",
            )
        account = self._get_owned_or_raise(account_id, current_user_id)

        try:
            client = get_cloud_provider_client(
                account.provider, decrypt_credentials(account.credentials_encrypted), account.region
            )
            client.destroy(region, resource_type, resource_id)
        except AppException as exc:
            self._audit(
                current_user_id, "cloud_resource_destroy", resource_type, account, region, resource_id, str(exc)
            )
            raise

        self._audit(
            current_user_id, "cloud_resource_destroy", resource_type, account, region, resource_id, "success"
        )

    def _get_owned_or_raise(self, account_id: int, current_user_id: int) -> CloudProviderAccount:
        account = self.repository.get_by_id(account_id)
        if account is None:
            raise NotFoundError(f"Cloud provider account {account_id} not found", code="CLOUD_ACCOUNT_NOT_FOUND")
        if account.user_id != current_user_id:
            raise ForbiddenError(
                "Cannot access another user's cloud provider account", code="NOT_YOUR_CLOUD_ACCOUNT"
            )
        return account

    def _audit(
        self,
        user_id: int,
        action: str,
        resource_type: str,
        account: CloudProviderAccount,
        region: str,
        resource_id: str | None,
        outcome: str,
    ) -> None:
        details = json.dumps(
            {
                "provider": account.provider,
                "cloud_provider_account_id": account.id,
                "region": region,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "outcome": outcome,
            }
        )
        self.db.add(
            AuditLog(
                user_id=user_id,
                action=action,
                entity_type=resource_type,
                # entity_id is an integer column - cloud resource ids (ARNs/
                # OCIDs/etc.) are strings, so the real identifier lives in
                # details above instead of being force-fit into this field.
                entity_id=None,
                details=details,
            )
        )
        self.db.commit()
