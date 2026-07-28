"""Business logic for cloud cost ingestion, querying, and monthly forecasting."""
from datetime import date

from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.integrations.aws_cost_explorer import fetch_monthly_costs_by_service as fetch_aws_costs
from app.integrations.azure_cost_management import (
    fetch_monthly_costs_by_service as fetch_azure_costs,
)
from app.models.cloud_cost import CloudCost
from app.models.user import User
from app.optimization.cost_forecaster import CostForecast, forecast_next_month
from app.repositories.cloud_cost_repository import CloudCostRepository
from app.repositories.cloud_provider_account_repository import CloudProviderAccountRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.cloud_cost import CloudCostCreate
from app.utils.crypto import decrypt_credentials
from app.utils.exceptions import ForbiddenError, NotFoundError, ValidationAppError
from app.utils.ownership import raise_if_cannot_access_project

# AWS and Azure are wired to real billing integrations (see
# app/integrations/aws_cost_explorer.py, azure_cost_management.py). GCP is
# deliberately not included: unlike AWS/Azure, GCP has no generalizable
# "give me my spend by service" API callable with just account credentials
# - it requires the customer to have already set up BigQuery billing
# export to a dataset only they control, which this platform can't assume
# or configure on their behalf. GCP cost sync therefore still reports the
# same honest CLOUD_SYNC_PROVIDER_NOT_SUPPORTED error below rather than
# faking a fragile integration - see app/integrations/gcp_monitoring.py's
# module docstring for the same disclosure on the metrics side.
_PROVIDER_COST_FETCHERS = {
    "aws": fetch_aws_costs,
    "azure": fetch_azure_costs,
}


class CloudCostService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = CloudCostRepository(db)
        self.project_repository = ProjectRepository(db)
        self.cloud_account_repository = CloudProviderAccountRepository(db)
        self.settings = get_settings()

    def _get_project_or_404(self, project_id: int, current_user: User):
        project = self.project_repository.get_by_id(project_id)
        if project is None:
            raise NotFoundError(f"Project {project_id} not found", code="PROJECT_NOT_FOUND")
        raise_if_cannot_access_project(project, current_user)
        return project

    def ingest(self, project_id: int, payload: CloudCostCreate, current_user: User) -> CloudCost:
        self._get_project_or_404(project_id, current_user)
        cost = CloudCost(
            project_id=project_id,
            provider=payload.provider,
            service_name=payload.service_name,
            cost_amount=payload.cost_amount,
            currency=payload.currency,
            billing_period_start=payload.billing_period_start,
            billing_period_end=payload.billing_period_end,
        )
        return self.repository.create(cost)

    def list(
        self,
        project_id: int,
        provider: str | None,
        since: date | None,
        until: date | None,
        page: int,
        page_size: int,
        current_user: User,
    ) -> tuple[list[CloudCost], int]:
        self._get_project_or_404(project_id, current_user)
        offset = (page - 1) * page_size
        return self.repository.search(project_id, provider, since, until, offset, page_size)

    def forecast(self, project_id: int, current_user: User) -> CostForecast:
        self._get_project_or_404(project_id, current_user)
        costs = self.repository.list_all_for_project(project_id)
        if not costs:
            raise NotFoundError(
                f"No cloud cost history for project {project_id} to forecast from",
                code="NO_COST_HISTORY",
            )
        return forecast_next_month(costs)

    def sync_cloud_costs(
        self, project_id: int, cloud_provider_account_id: int, current_user: User
    ) -> "list[CloudCost]":
        """Pulls real billing data (AWS Cost Explorer or Azure Cost
        Management - see _PROVIDER_COST_FETCHERS) for the account and
        stores it against this project, replacing what would otherwise be
        manually-entered CloudCostCreate rows (Phase 18, audit roadmap
        item 9). Skips months already synced for the same service so
        repeated syncs (e.g. a scheduled monthly run) don't duplicate
        already-billed history."""
        self._get_project_or_404(project_id, current_user)

        account = self.cloud_account_repository.get_by_id(cloud_provider_account_id)
        if account is None:
            raise NotFoundError(
                f"Cloud provider account {cloud_provider_account_id} not found",
                code="CLOUD_ACCOUNT_NOT_FOUND",
            )
        if account.user_id != current_user.id:
            raise ForbiddenError(
                "Cannot sync billing data using another user's cloud provider account",
                code="NOT_YOUR_CLOUD_ACCOUNT",
            )

        fetcher = _PROVIDER_COST_FETCHERS.get(account.provider)
        if fetcher is None:
            raise ValidationAppError(
                f"Real billing sync is not yet implemented for provider '{account.provider}' - "
                f"only {', '.join(sorted(_PROVIDER_COST_FETCHERS))} are currently supported",
                code="COST_SYNC_PROVIDER_NOT_SUPPORTED",
            )

        credentials = decrypt_credentials(account.credentials_encrypted)
        monthly_costs = fetcher(credentials, self.settings.CLOUD_COST_SYNC_LOOKBACK_MONTHS)

        created: list[CloudCost] = []
        for entry in monthly_costs:
            if self.repository.get_existing(
                project_id, account.provider, entry["service_name"], entry["billing_period_start"]
            ):
                continue
            cost = CloudCost(
                project_id=project_id,
                provider=account.provider,
                service_name=entry["service_name"],
                cost_amount=entry["cost_amount"],
                currency=entry["currency"],
                billing_period_start=entry["billing_period_start"],
                billing_period_end=entry["billing_period_end"],
            )
            created.append(self.repository.create(cost))

        return created
