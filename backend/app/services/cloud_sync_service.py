"""Business logic for pulling real-time telemetry from a deployment's linked
cloud provider account, replacing manually-posted/synthetic resource_usage
data with genuine cloud provider metrics (Phase 12).

Only the "aws" provider is wired to a real integration in this pass (see
app/integrations/aws_cloudwatch.py) - any other provider value raises a
clear, honest CLOUD_SYNC_PROVIDER_NOT_SUPPORTED error rather than silently
doing nothing, since Azure/GCP support would need their own dedicated SDK
integration modules following the same pattern (see docs/PHASE_12.md).
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.integrations.aws_cloudwatch import fetch_ec2_resource_usage
from app.models.deployment import Deployment
from app.models.resource_usage import ResourceUsage
from app.repositories.cloud_provider_account_repository import CloudProviderAccountRepository
from app.repositories.deployment_repository import DeploymentRepository
from app.repositories.resource_usage_repository import ResourceUsageRepository
from app.schemas.cloud_sync import CloudSyncAllSummary, CloudSyncResult
from app.utils.crypto import decrypt_credentials
from app.utils.exceptions import NotFoundError, ValidationAppError
from app.utils.logger import get_logger

logger = get_logger("cloud_sync")

_PROVIDER_FETCHERS = {
    "aws": fetch_ec2_resource_usage,
}


class CloudSyncService:
    def __init__(self, db: Session):
        self.db = db
        self.deployment_repository = DeploymentRepository(db)
        self.cloud_account_repository = CloudProviderAccountRepository(db)
        self.resource_usage_repository = ResourceUsageRepository(db)

    def sync_deployment(self, deployment_id: int) -> CloudSyncResult:
        deployment = self.deployment_repository.get_by_id(deployment_id)
        if deployment is None:
            raise NotFoundError(f"Deployment {deployment_id} not found", code="DEPLOYMENT_NOT_FOUND")

        if deployment.cloud_provider_account_id is None or deployment.cloud_resource_identifier is None:
            raise ValidationAppError(
                "This deployment has no linked cloud provider account and resource identifier - "
                "set both via PUT /deployments/{id} before syncing",
                code="CLOUD_SYNC_NOT_CONFIGURED",
            )

        account = self.cloud_account_repository.get_by_id(deployment.cloud_provider_account_id)
        if account is None:
            raise NotFoundError(
                f"Cloud provider account {deployment.cloud_provider_account_id} not found",
                code="CLOUD_ACCOUNT_NOT_FOUND",
            )

        fetcher = _PROVIDER_FETCHERS.get(account.provider)
        if fetcher is None:
            raise ValidationAppError(
                f"Real-time sync is not yet implemented for provider '{account.provider}' - "
                f"only {', '.join(sorted(_PROVIDER_FETCHERS))} are currently supported",
                code="CLOUD_SYNC_PROVIDER_NOT_SUPPORTED",
            )

        credentials = decrypt_credentials(account.credentials_encrypted)
        usage_data = fetcher(
            credentials, account.region, deployment.cloud_resource_identifier, self._lookback_minutes()
        )

        usage = ResourceUsage(
            deployment_id=deployment.id,
            cpu_usage_percent=usage_data["cpu_usage_percent"],
            memory_usage_mb=usage_data["memory_usage_mb"],
            disk_usage_mb=usage_data["disk_usage_mb"],
            network_in_kbps=usage_data["network_in_kbps"],
            network_out_kbps=usage_data["network_out_kbps"],
            recorded_at=usage_data["recorded_at"],
        )
        usage = self.resource_usage_repository.create(usage)

        logger.info(
            "Synced real cloud metrics for deployment %s from %s account %s (resource %s)",
            deployment.id,
            account.provider,
            account.id,
            deployment.cloud_resource_identifier,
        )

        return CloudSyncResult(
            deployment_id=deployment.id,
            cloud_provider_account_id=account.id,
            provider=account.provider,
            resource_identifier=deployment.cloud_resource_identifier,
            synced_at=datetime.now(timezone.utc),
            resource_usage_id=usage.id,
        )

    def sync_all(self) -> CloudSyncAllSummary:
        """Called by the scheduled job (see app/integrations/scheduler.py) -
        syncs every cloud-linked deployment, tolerating individual failures
        (e.g. one account's credentials expired) without aborting the rest."""
        deployments: list[Deployment] = self.deployment_repository.list_cloud_linked()
        synced = 0
        failed = 0
        for deployment in deployments:
            try:
                self.sync_deployment(deployment.id)
                synced += 1
            except Exception:
                failed += 1
                logger.exception(
                    "Scheduled cloud sync failed for deployment %s", deployment.id
                )
        return CloudSyncAllSummary(
            deployments_attempted=len(deployments), deployments_synced=synced, deployments_failed=failed
        )

    @staticmethod
    def _lookback_minutes() -> int:
        return get_settings().CLOUD_SYNC_LOOKBACK_MINUTES
