"""Business logic for cloud cost ingestion, querying, and monthly forecasting."""
from datetime import date

from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.integrations.aws_cost_explorer import fetch_monthly_costs_by_service
from app.models.cloud_cost import CloudCost
from app.optimization.cost_forecaster import CostForecast, forecast_next_month
from app.repositories.cloud_cost_repository import CloudCostRepository
from app.repositories.cloud_provider_account_repository import CloudProviderAccountRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.cloud_cost import CloudCostCreate
from app.utils.crypto import decrypt_credentials
from app.utils.exceptions import ForbiddenError, NotFoundError, ValidationAppError

# Only AWS is wired to a real billing integration in this pass (see
# app/integrations/aws_cost_explorer.py) - mirrors the same
# one-provider-for-now honesty as CloudSyncService for metrics.
_PROVIDER_COST_FETCHERS = {
    "aws": fetch_monthly_costs_by_service,
}


class CloudCostService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = CloudCostRepository(db)
        self.project_repository = ProjectRepository(db)
        self.cloud_account_repository = CloudProviderAccountRepository(db)
        self.settings = get_settings()

    def _get_project_or_404(self, project_id: int):
        project = self.project_repository.get_by_id(project_id)
        if project is None:
            raise NotFoundError(f"Project {project_id} not found", code="PROJECT_NOT_FOUND")
        return project

    def ingest(self, project_id: int, payload: CloudCostCreate) -> CloudCost:
        self._get_project_or_404(project_id)
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
    ) -> tuple[list[CloudCost], int]:
        self._get_project_or_404(project_id)
        offset = (page - 1) * page_size
        return self.repository.search(project_id, provider, since, until, offset, page_size)

    def forecast(self, project_id: int) -> CostForecast:
        self._get_project_or_404(project_id)
        costs = self.repository.list_all_for_project(project_id)
        if not costs:
            raise NotFoundError(
                f"No cloud cost history for project {project_id} to forecast from",
                code="NO_COST_HISTORY",
            )
        return forecast_next_month(costs)

    def sync_from_aws(
        self, project_id: int, cloud_provider_account_id: int, current_user_id: int
    ) -> "list[CloudCost]":
        """Pulls real AWS Cost Explorer billing data for the account and
        stores it against this project, replacing what would otherwise be
        manually-entered CloudCostCreate rows (Phase 18, audit roadmap
        item 9). Skips months already synced for the same service so
        repeated syncs (e.g. a scheduled monthly run) don't duplicate
        already-billed history."""
        self._get_project_or_404(project_id)

        account = self.cloud_account_repository.get_by_id(cloud_provider_account_id)
        if account is None:
            raise NotFoundError(
                f"Cloud provider account {cloud_provider_account_id} not found",
                code="CLOUD_ACCOUNT_NOT_FOUND",
            )
        if account.user_id != current_user_id:
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
