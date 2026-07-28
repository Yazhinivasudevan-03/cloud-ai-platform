"""GCP CloudProviderClient adapter (Phase 25) - wraps the existing, already
real GCP fetcher function (app/integrations/gcp_monitoring.py) for
list_monitoring, and adds a genuinely new real call for list_regions via
`google-cloud-compute`'s RegionsClient - Compute Engine's own regions API,
never a hardcoded list. list_costs is deliberately NOT implemented (raises
the base class's "not yet supported" error) - unlike AWS/Azure, GCP has no
generalizable "spend by service" API callable with just account
credentials (see gcp_monitoring.py's own docstring for the same disclosed
limitation, carried forward here rather than worked around).
"""
import json

import tenacity
from google.api_core.exceptions import (
    DeadlineExceeded,
    GoogleAPICallError,
    PermissionDenied,
    ServiceUnavailable,
    Unauthenticated,
)
from google.cloud import compute_v1
from google.oauth2 import service_account

from app.integrations.cloud_provider_client import CloudProviderClient, CloudRegionInfo, ResourceUsageSnapshot
from app.integrations.gcp_monitoring import fetch_instance_resource_usage
from app.utils.exceptions import ValidationAppError

# Compute Engine's Region resource has no dedicated human-readable display
# name field (unlike Azure's) - this table is presentation-only labelling
# for regions the live API actually returned, with a raw-id fallback for
# anything unmapped (see aws_provider.py's identical disclosure).
_GCP_REGION_DISPLAY_NAMES = {
    "us-central1": "Iowa",
    "us-east1": "South Carolina",
    "us-east4": "Northern Virginia",
    "us-west1": "Oregon",
    "us-west2": "Los Angeles",
    "europe-west1": "Belgium",
    "europe-west2": "London",
    "europe-west3": "Frankfurt",
    "europe-north1": "Finland",
    "asia-south1": "Mumbai",
    "asia-southeast1": "Singapore",
    "asia-northeast1": "Tokyo",
    "australia-southeast1": "Sydney",
}


def _is_retryable_gcp_error(exc: BaseException) -> bool:
    return isinstance(exc, (ServiceUnavailable, DeadlineExceeded))


_gcp_retry = tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable_gcp_error),
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)


class GcpCloudProviderClient(CloudProviderClient):
    @property
    def provider_name(self) -> str:
        return "gcp"

    def _load_credentials(self) -> tuple[service_account.Credentials, str]:
        service_account_json = self.credentials.get("service_account_json")
        if not service_account_json:
            raise ValidationAppError(
                "GCP credentials must include 'service_account_json' (the full service "
                "account key JSON, as a string)",
                code="GCP_CREDENTIALS_INCOMPLETE",
            )
        try:
            service_account_info = json.loads(service_account_json)
        except (TypeError, ValueError) as exc:
            raise ValidationAppError(
                "GCP credentials 'service_account_json' is not valid JSON",
                code="GCP_CREDENTIALS_INCOMPLETE",
            ) from exc

        project_id = self.credentials.get("project_id") or service_account_info.get("project_id")
        if not project_id:
            raise ValidationAppError(
                "GCP credentials must include 'project_id' (or a service_account_json "
                "that itself contains one)",
                code="GCP_CREDENTIALS_INCOMPLETE",
            )
        return service_account.Credentials.from_service_account_info(service_account_info), project_id

    def authenticate(self) -> None:
        self._load_credentials()

    def list_regions(self) -> list[CloudRegionInfo]:
        google_credentials, project_id = self._load_credentials()
        client = compute_v1.RegionsClient(credentials=google_credentials)

        @_gcp_retry
        def _list_regions():
            return list(client.list(project=project_id))

        try:
            regions = _list_regions()
        except (PermissionDenied, Unauthenticated) as exc:
            raise ValidationAppError(
                f"GCP rejected the credentials: {exc}", code="GCP_REGION_DISCOVERY_FAILED"
            ) from exc
        except GoogleAPICallError as exc:
            raise ValidationAppError(
                f"GCP rejected the region-discovery request: {exc}", code="GCP_REGION_DISCOVERY_FAILED"
            ) from exc

        return [
            {"id": region.name, "display_name": _GCP_REGION_DISPLAY_NAMES.get(region.name, region.name)}
            for region in regions
        ]

    def list_projects(self) -> list[str]:
        _, project_id = self._load_credentials()
        return [project_id]

    def list_monitoring(self, resource_id: str, lookback_minutes: int) -> ResourceUsageSnapshot:
        return fetch_instance_resource_usage(self.credentials, self.region, resource_id, lookback_minutes)  # type: ignore[return-value]
