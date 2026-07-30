"""DigitalOcean CloudProviderClient adapter (Phase 27) - the first genuine
backend integration DigitalOcean has ever had in this platform (previously
a UI-only "connect" button since Phase 24). Built against `pydo`,
DigitalOcean's own official Python client (generated from their public API
v2 spec) - authenticated with a single personal access token, the same
"one primary credential" simplicity every other provider here already has.

Honesty note (same disclosed limitation as OCI/Alibaba/IBM - see their own
docstrings): there is no DigitalOcean emulator available and no live
account to validate this against, so this module is verified only against
mocked SDK client responses (see tests/test_digitalocean_provider.py),
never a real request/response round trip.

Credentials dict shape: {"api_token": "<personal access token>",
"spaces_access_key_id": "<optional, required only for Spaces storage>",
"spaces_secret_access_key": "<optional, required only for Spaces
storage>"} - Spaces (DigitalOcean's S3-compatible object storage) is
authenticated with its own separate access-key/secret-key pair, not the
API token, a genuine DigitalOcean platform distinction this adapter
discloses rather than papers over.

`pydo` is generated with the same autorest tooling Azure's own SDKs use,
so it raises `azure.core.exceptions.HttpResponseError` on any rejected
request (confirmed empirically against the installed package) - the same
exception type azure_provider.py already handles, not a DigitalOcean-
specific class.
"""
import boto3
import botocore.exceptions
import pydo
import tenacity
from azure.core.exceptions import HttpResponseError

from app.integrations.cloud_provider_client import (
    CloudProviderClient,
    CloudRegionInfo,
    CloudResourceSummary,
    MonthlyServiceCost,
    ResourceUsageSnapshot,
)
from app.integrations.digitalocean_billing import fetch_monthly_costs_by_service as fetch_do_monthly_costs
from app.integrations.digitalocean_monitoring import fetch_droplet_resource_usage
from app.utils.exceptions import ValidationAppError

# The one, fixed, smallest Droplet size slug deploy() will ever request -
# not user-configurable in this pass (see aws_provider.py's identical
# _DEPLOY_INSTANCE_TYPE for the same reasoning).
_DEPLOY_SIZE = "s-1vcpu-1gb"

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _is_retryable_do_error(exc: BaseException) -> bool:
    return isinstance(exc, HttpResponseError) and exc.status_code in _RETRYABLE_STATUS_CODES


_do_retry = tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable_do_error),
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)


# Phase 25E-style region-discovery error taxonomy (see aws_provider.py's
# identical rationale) - HttpResponseError already exposes a real HTTP
# status per failure, so the categories below are read directly from it.
def _classify_do_region_error(exc: HttpResponseError) -> tuple[str, str]:
    status = exc.status_code
    message = exc.message or str(exc)
    if status in (401,):
        return "DIGITALOCEAN_REGION_CREDENTIALS_REJECTED", f"DigitalOcean rejected the credentials: {message}"
    if status == 403:
        return "DIGITALOCEAN_REGION_ACCESS_DENIED", f"DigitalOcean denied access to the region-discovery request: {message}"
    if status == 429:
        return (
            "DIGITALOCEAN_REGION_THROTTLED",
            f"DigitalOcean throttled the region-discovery request even after retries: {message}",
        )
    if status is not None and status >= 500:
        return "DIGITALOCEAN_REGION_PROVIDER_OUTAGE", f"DigitalOcean reported a service outage: {message}"
    return "DIGITALOCEAN_REGION_DISCOVERY_FAILED", f"DigitalOcean rejected the region-discovery request: {message}"


class DigitalOceanCloudProviderClient(CloudProviderClient):
    @property
    def provider_name(self) -> str:
        return "digitalocean"

    def authenticate(self) -> None:
        if not self.credentials.get("api_token"):
            raise ValidationAppError(
                "DigitalOcean credentials must include 'api_token' (a personal access token)",
                code="DIGITALOCEAN_CREDENTIALS_INCOMPLETE",
            )

    def _client(self) -> pydo.Client:
        self.authenticate()
        return pydo.Client(token=self.credentials["api_token"])

    def _spaces_client(self, region: str):
        access_key = self.credentials.get("spaces_access_key_id")
        secret_key = self.credentials.get("spaces_secret_access_key")
        if not access_key or not secret_key:
            raise ValidationAppError(
                "DigitalOcean Spaces (storage) operations require credentials.spaces_access_key_id "
                "and credentials.spaces_secret_access_key - a separate key pair from the API token, "
                "generated on the Spaces Keys page",
                code="DIGITALOCEAN_SPACES_NOT_CONFIGURED",
            )
        return boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=f"https://{region}.digitaloceanspaces.com",
        )

    def list_regions(self) -> list[CloudRegionInfo]:
        client = self._client()

        @_do_retry
        def _list_regions():
            return client.regions.list()

        try:
            response = _list_regions()
        except HttpResponseError as exc:
            code, message = _classify_do_region_error(exc)
            raise ValidationAppError(message, code=code) from exc

        regions = [
            {"id": entry["slug"], "display_name": entry["name"]}
            for entry in response.get("regions", [])
            if entry.get("available", True)
        ]
        if not regions:
            raise ValidationAppError(
                "DigitalOcean returned zero available regions for this account - unexpected for a "
                "working account, and treated as a failure rather than a legitimately empty result",
                code="DIGITALOCEAN_REGION_NO_REGIONS_RETURNED",
            )
        return regions

    def list_projects(self) -> list[str]:
        account_id, _, _ = self._identity()
        return [account_id] if account_id else []

    def _identity(self) -> tuple[str | None, str | None, str | None]:
        # Best-effort only - the base class's test_connection() has already
        # proven the credentials work via a real list_regions() call by the
        # time this runs.
        try:
            account = self._client().account.get().get("account", {})
            return account.get("uuid"), None, account.get("email")
        except HttpResponseError:
            return None, None, None

    def list_monitoring(self, resource_id: str, lookback_minutes: int) -> ResourceUsageSnapshot:
        return fetch_droplet_resource_usage(self.credentials, self.region, resource_id, lookback_minutes)  # type: ignore[return-value]

    def list_costs(self, months: int) -> list[MonthlyServiceCost]:
        return fetch_do_monthly_costs(self.credentials, months)

    def _wrap_http_error(self, exc: HttpResponseError, code: str) -> ValidationAppError:
        return ValidationAppError(f"DigitalOcean rejected the request: {exc.message or exc}", code=code)

    def list_resources(self, region: str) -> list[CloudResourceSummary]:
        client = self._client()

        @_do_retry
        def _list_droplets():
            return client.droplets.list()

        try:
            response = _list_droplets()
        except HttpResponseError as exc:
            raise self._wrap_http_error(exc, "DIGITALOCEAN_RESOURCE_INVENTORY_FAILED") from exc

        return [
            {
                "id": str(droplet["id"]),
                "name": droplet["name"],
                "type": droplet.get("size_slug", "unknown"),
                "region": region,
                "status": droplet.get("status", "unknown"),
                "created_at": droplet.get("created_at"),
            }
            for droplet in response.get("droplets", [])
            if droplet.get("region", {}).get("slug") == region
        ]

    def list_clusters(self, region: str) -> list[CloudResourceSummary]:
        client = self._client()

        @_do_retry
        def _list_clusters():
            return client.kubernetes.list_clusters()

        try:
            response = _list_clusters()
        except HttpResponseError as exc:
            raise self._wrap_http_error(exc, "DIGITALOCEAN_CLUSTER_INVENTORY_FAILED") from exc

        return [
            {
                "id": cluster["id"],
                "name": cluster["name"],
                "type": "doks",
                "region": region,
                "status": cluster.get("status", {}).get("state", "unknown"),
                "created_at": cluster.get("created_at"),
            }
            for cluster in response.get("kubernetes_clusters", [])
            if cluster.get("region") == region
        ]

    def list_databases(self, region: str) -> list[CloudResourceSummary]:
        client = self._client()

        @_do_retry
        def _list_databases():
            return client.databases.list_clusters()

        try:
            response = _list_databases()
        except HttpResponseError as exc:
            raise self._wrap_http_error(exc, "DIGITALOCEAN_DATABASE_INVENTORY_FAILED") from exc

        return [
            {
                "id": db["id"],
                "name": db["name"],
                "type": db.get("engine", "unknown"),
                "region": region,
                "status": db.get("status", "unknown"),
                "created_at": db.get("created_at"),
            }
            for db in response.get("databases", [])
            if db.get("region") == region
        ]

    def list_storage(self, region: str) -> list[CloudResourceSummary]:
        client = self._spaces_client(region)
        try:
            response = client.list_buckets()
        except botocore.exceptions.ClientError as exc:
            raise ValidationAppError(
                f"DigitalOcean Spaces rejected the storage-inventory request: {exc}",
                code="DIGITALOCEAN_STORAGE_INVENTORY_FAILED",
            ) from exc

        return [
            {
                "id": bucket["Name"],
                "name": bucket["Name"],
                "type": "spaces_bucket",
                "region": region,
                "status": "available",
                "created_at": bucket.get("CreationDate"),
            }
            for bucket in response.get("Buckets", [])
        ]

    def list_networking(self, region: str) -> list[CloudResourceSummary]:
        client = self._client()

        @_do_retry
        def _list_vpcs():
            return client.vpcs.list()

        try:
            response = _list_vpcs()
        except HttpResponseError as exc:
            raise self._wrap_http_error(exc, "DIGITALOCEAN_NETWORKING_INVENTORY_FAILED") from exc

        return [
            {
                "id": vpc["id"],
                "name": vpc["name"],
                "type": "vpc",
                "region": region,
                "status": "available",
                "created_at": vpc.get("created_at"),
            }
            for vpc in response.get("vpcs", [])
            if vpc.get("region") == region
        ]

    def deploy(self, region: str, resource_type: str, spec: dict) -> CloudResourceSummary:
        if resource_type == "compute":
            return self._deploy_compute(region, spec)
        if resource_type == "storage":
            return self._deploy_storage(region, spec)
        if resource_type == "networking":
            return self._deploy_networking(region, spec)
        raise self._not_yet_supported(f"Provisioning of '{resource_type}'")

    def destroy(self, region: str, resource_type: str, resource_id: str) -> None:
        if resource_type == "compute":
            return self._destroy_compute(resource_id)
        if resource_type == "storage":
            return self._destroy_storage(region, resource_id)
        if resource_type == "networking":
            return self._destroy_networking(resource_id)
        raise self._not_yet_supported(f"Provisioning of '{resource_type}'")

    def _deploy_compute(self, region: str, spec: dict) -> CloudResourceSummary:
        # A real Droplet needs an image - a real, standard DigitalOcean
        # prerequisite this platform cannot fabricate on the caller's
        # behalf (the same honest stance as requiring an AMI id for AWS).
        image = spec.get("image")
        if not image:
            raise ValidationAppError(
                "DigitalOcean compute deploy requires spec.image (an image slug or numeric ID, "
                "e.g. 'ubuntu-22-04-x64')",
                code="DIGITALOCEAN_DEPLOY_SPEC_INCOMPLETE",
            )
        client = self._client()
        name = spec.get("name", "cloud-ai-platform-droplet")
        body = {"name": name, "region": region, "size": _DEPLOY_SIZE, "image": image}
        if spec.get("vpc_uuid"):
            body["vpc_uuid"] = spec["vpc_uuid"]
        try:
            response = client.droplets.create(body=body)
        except HttpResponseError as exc:
            raise self._wrap_http_error(exc, "DIGITALOCEAN_DEPLOY_FAILED") from exc

        droplet = response["droplet"]
        return {
            "id": str(droplet["id"]),
            "name": droplet["name"],
            "type": _DEPLOY_SIZE,
            "region": region,
            "status": droplet.get("status", "unknown"),
            "created_at": droplet.get("created_at"),
        }

    def _destroy_compute(self, resource_id: str) -> None:
        client = self._client()
        try:
            client.droplets.destroy(droplet_id=int(resource_id))
        except HttpResponseError as exc:
            raise self._wrap_http_error(exc, "DIGITALOCEAN_DESTROY_FAILED") from exc

    def _deploy_storage(self, region: str, spec: dict) -> CloudResourceSummary:
        name = spec.get("name")
        if not name:
            raise ValidationAppError(
                "DigitalOcean storage deploy requires spec.name (a globally-unique Spaces bucket name)",
                code="DIGITALOCEAN_DEPLOY_SPEC_INCOMPLETE",
            )
        client = self._spaces_client(region)
        try:
            client.create_bucket(Bucket=name)
        except botocore.exceptions.ClientError as exc:
            raise ValidationAppError(
                f"DigitalOcean Spaces rejected the deploy request: {exc}", code="DIGITALOCEAN_DEPLOY_FAILED"
            ) from exc

        return {"id": name, "name": name, "type": "spaces_bucket", "region": region, "status": "available", "created_at": None}

    def _destroy_storage(self, region: str, resource_id: str) -> None:
        client = self._spaces_client(region)
        try:
            # Requires an already-empty bucket - a real Spaces precondition
            # this platform does not attempt to bypass by force-emptying it.
            client.delete_bucket(Bucket=resource_id)
        except botocore.exceptions.ClientError as exc:
            raise ValidationAppError(
                f"DigitalOcean Spaces rejected the destroy request: {exc}", code="DIGITALOCEAN_DESTROY_FAILED"
            ) from exc

    def _deploy_networking(self, region: str, spec: dict) -> CloudResourceSummary:
        client = self._client()
        name = spec.get("name", "cloud-ai-platform-vpc")
        try:
            response = client.vpcs.create(body={"name": name, "region": region})
        except HttpResponseError as exc:
            raise self._wrap_http_error(exc, "DIGITALOCEAN_DEPLOY_FAILED") from exc

        vpc = response["vpc"]
        return {
            "id": vpc["id"],
            "name": vpc["name"],
            "type": "vpc",
            "region": region,
            "status": "available",
            "created_at": vpc.get("created_at"),
        }

    def _destroy_networking(self, resource_id: str) -> None:
        client = self._client()
        try:
            client.vpcs.delete(vpc_id=resource_id)
        except HttpResponseError as exc:
            raise self._wrap_http_error(exc, "DIGITALOCEAN_DESTROY_FAILED") from exc
