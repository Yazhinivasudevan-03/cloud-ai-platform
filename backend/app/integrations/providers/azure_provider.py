"""Azure CloudProviderClient adapter (Phase 25) - wraps the existing, already
real Azure fetcher functions (app/integrations/azure_monitor.py,
azure_cost_management.py) for list_monitoring/list_costs, and adds a
genuinely new real call for list_regions/list_projects via
`azure-mgmt-resource`'s SubscriptionClient - Azure Resource Manager's own
"Subscriptions -> List Locations" API, never a hardcoded list. Unlike AWS,
Azure's own API already returns a real human-readable `display_name` per
region, so no presentation-only lookup table is needed here.
"""
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError, ServiceRequestError
from azure.identity import ClientSecretCredential
from azure.mgmt.resource import SubscriptionClient
import tenacity

from app.integrations.azure_cost_management import fetch_monthly_costs_by_service
from app.integrations.azure_monitor import fetch_vm_resource_usage
from app.integrations.cloud_provider_client import (
    CloudProviderClient,
    CloudRegionInfo,
    MonthlyServiceCost,
    ResourceUsageSnapshot,
)
from app.utils.exceptions import ValidationAppError

_RETRYABLE_STATUS_CODES = {429, 500, 503}


def _is_retryable_azure_error(exc: BaseException) -> bool:
    if isinstance(exc, HttpResponseError):
        return exc.status_code in _RETRYABLE_STATUS_CODES
    return isinstance(exc, ServiceRequestError)


_azure_retry = tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable_azure_error),
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)


class AzureCloudProviderClient(CloudProviderClient):
    @property
    def provider_name(self) -> str:
        return "azure"

    def authenticate(self) -> None:
        if not all(
            self.credentials.get(key) for key in ("tenant_id", "client_id", "client_secret", "subscription_id")
        ):
            raise ValidationAppError(
                "Azure credentials must include 'tenant_id', 'client_id', 'client_secret' "
                "and 'subscription_id'",
                code="AZURE_CREDENTIALS_INCOMPLETE",
            )

    def _credential(self) -> ClientSecretCredential:
        self.authenticate()
        return ClientSecretCredential(
            self.credentials["tenant_id"], self.credentials["client_id"], self.credentials["client_secret"]
        )

    def list_regions(self) -> list[CloudRegionInfo]:
        client = SubscriptionClient(self._credential())
        subscription_id = self.credentials["subscription_id"]

        @_azure_retry
        def _list_locations():
            return list(client.subscriptions.list_locations(subscription_id))

        try:
            locations = _list_locations()
        except ClientAuthenticationError as exc:
            raise ValidationAppError(
                f"Azure rejected the credentials: {exc}", code="AZURE_REGION_DISCOVERY_FAILED"
            ) from exc
        except HttpResponseError as exc:
            raise ValidationAppError(
                f"Azure rejected the region-discovery request: {exc.message or exc}",
                code="AZURE_REGION_DISCOVERY_FAILED",
            ) from exc
        except ServiceRequestError as exc:
            raise ValidationAppError(
                f"Could not reach Azure to discover regions: {exc}", code="AZURE_REGION_DISCOVERY_FAILED"
            ) from exc

        return [
            {"id": location.name, "display_name": location.display_name or location.name}
            for location in locations
        ]

    def list_projects(self) -> list[str]:
        client = SubscriptionClient(self._credential())
        try:
            subscriptions = list(client.subscriptions.list())
        except ClientAuthenticationError as exc:
            raise ValidationAppError(
                f"Azure rejected the credentials: {exc}", code="AZURE_IDENTITY_REQUEST_FAILED"
            ) from exc
        except HttpResponseError as exc:
            raise ValidationAppError(
                f"Azure rejected the subscription-listing request: {exc.message or exc}",
                code="AZURE_IDENTITY_REQUEST_FAILED",
            ) from exc
        return [subscription.subscription_id for subscription in subscriptions]

    def list_monitoring(self, resource_id: str, lookback_minutes: int) -> ResourceUsageSnapshot:
        return fetch_vm_resource_usage(self.credentials, self.region, resource_id, lookback_minutes)  # type: ignore[return-value]

    def list_costs(self, months: int) -> list[MonthlyServiceCost]:
        return fetch_monthly_costs_by_service(self.credentials, months)
