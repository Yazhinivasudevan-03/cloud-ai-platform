"""IBM Cloud CloudProviderClient adapter (Phase 27) - the first genuine
backend integration IBM Cloud has ever had in this platform (previously a
UI-only "connect" button since Phase 24, storing credentials but never
calling a real IBM Cloud API). Built against the official
`ibm-vpc`/`ibm-platform-services`/`ibm-cos-sdk` SDKs, all authenticated via
a single IAM API key - the same "one primary credential" simplicity every
other provider in this platform already has.

Honesty note (same disclosed limitation as OCI/Alibaba - see their own
docstrings): there is no IBM Cloud emulator available and no live account
to validate this against, so this module is verified only against mocked
SDK client responses (see tests/test_ibm_provider.py), never a real
request/response round trip.

Credentials dict shape: {"api_key": "<IAM API key>", "resource_group_id":
"<optional, required only for provisioning>", "cos_instance_crn":
"<optional, required only for storage - the specific Cloud Object Storage
service instance's CRN buckets are created/listed under>"}.

IBM Cloud has no single "list all databases"/"list all clusters" API the
way AWS/Azure/GCP do - every managed service (Kubernetes Service,
OpenShift, each of the ~10 "Databases for X" products) is its own Resource
Controller service instance. This adapter derives clusters/databases from
`ResourceControllerV2.list_resource_instances()` by filtering each
instance's own CRN service-name segment against IBM's real, stable naming
convention ("containers-kubernetes"/"containers-kubernetes-openshift" for
clusters, every "databases-for-*" service for databases) - a genuine,
disclosed derivation, not a fabricated filter.
"""
from datetime import datetime

import ibm_boto3
import ibm_botocore.client
import ibm_botocore.exceptions
import ibm_platform_services
import ibm_vpc
import tenacity
from ibm_cloud_sdk_core.api_exception import ApiException
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator

from app.integrations.cloud_provider_client import (
    CloudProviderClient,
    CloudRegionInfo,
    CloudResourceSummary,
)
from app.utils.exceptions import ValidationAppError

# IBM VPC's list_regions() returns only region slugs (e.g. "us-south"),
# never a human-readable display name - same presentation-only lookup
# pattern as aws_provider.py/gcp_provider.py/oci_provider.py, falling back
# to the raw slug for anything unmapped.
_IBM_REGION_DISPLAY_NAMES = {
    "us-south": "US South (Dallas)",
    "us-east": "US East (Washington DC)",
    "eu-gb": "United Kingdom (London)",
    "eu-de": "Germany (Frankfurt)",
    "eu-es": "Spain (Madrid)",
    "jp-tok": "Japan (Tokyo)",
    "jp-osa": "Japan (Osaka)",
    "au-syd": "Australia (Sydney)",
    "br-sao": "Brazil (Sao Paulo)",
    "ca-tor": "Canada (Toronto)",
}

_KUBERNETES_SERVICE_NAMES = {"containers-kubernetes", "containers-kubernetes-openshift"}

# The one, fixed, smallest standard general-purpose VPC profile deploy()
# will ever request - not user-configurable in this pass (see
# aws_provider.py's identical _DEPLOY_INSTANCE_TYPE for the same reasoning).
_DEPLOY_PROFILE = "bx2-2x8"


def _is_retryable_ibm_error(exc: BaseException) -> bool:
    return isinstance(exc, ApiException) and exc.status_code in (429, 500, 502, 503, 504)


_ibm_retry = tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable_ibm_error),
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)


# Phase 25E-style region-discovery error taxonomy (see aws_provider.py's
# identical rationale) - IBM's ApiException already exposes a real HTTP
# status per failure, so the categories below are read directly from it.
# IBM's IAM token endpoint rejects an unknown/invalid API key with a plain
# 400 (Bad Request), not 401 - confirmed empirically via live verification
# against the real IBM Cloud IAM API (see docs/PHASE_27.md), so 400 is
# treated as a credentials failure here too, not folded into the generic
# fallback below.
def _classify_ibm_region_error(exc: ApiException) -> tuple[str, str]:
    message = f"IBM Cloud rejected the region-discovery request ({exc.status_code}): {exc.message}"
    if exc.status_code in (400, 401):
        return "IBM_REGION_CREDENTIALS_REJECTED", f"IBM Cloud rejected the credentials: {exc.message}"
    if exc.status_code == 403:
        return "IBM_REGION_ACCESS_DENIED", message
    if exc.status_code == 429:
        return "IBM_REGION_THROTTLED", f"IBM Cloud throttled the region-discovery request even after retries: {exc.message}"
    if exc.status_code >= 500:
        return "IBM_REGION_PROVIDER_OUTAGE", f"IBM Cloud reported a service outage: {exc.message}"
    return "IBM_REGION_DISCOVERY_FAILED", message


class IbmCloudProviderClient(CloudProviderClient):
    @property
    def provider_name(self) -> str:
        return "ibm"

    def authenticate(self) -> None:
        if not self.credentials.get("api_key"):
            raise ValidationAppError(
                "IBM Cloud credentials must include 'api_key' (an IAM API key)",
                code="IBM_CREDENTIALS_INCOMPLETE",
            )

    def _authenticator(self) -> IAMAuthenticator:
        self.authenticate()
        return IAMAuthenticator(apikey=self.credentials["api_key"])

    def _vpc_client_for(self, region: str) -> ibm_vpc.VpcV1:
        client = ibm_vpc.VpcV1(authenticator=self._authenticator())
        client.set_service_url(f"https://{region}.iaas.cloud.ibm.com/v1")
        return client

    def _resource_controller_client(self) -> ibm_platform_services.ResourceControllerV2:
        return ibm_platform_services.ResourceControllerV2(authenticator=self._authenticator())

    def _cos_client(self, region: str):
        cos_instance_crn = self.credentials.get("cos_instance_crn")
        if not cos_instance_crn:
            raise ValidationAppError(
                "IBM Cloud storage operations require credentials.cos_instance_crn (the CRN of the "
                "Cloud Object Storage service instance to use)",
                code="IBM_COS_INSTANCE_NOT_CONFIGURED",
            )
        return ibm_boto3.client(
            "s3",
            ibm_api_key_id=self.credentials["api_key"],
            ibm_service_instance_id=cos_instance_crn,
            config=ibm_botocore.client.Config(signature_version="oauth"),
            endpoint_url=f"https://s3.{region}.cloud-object-storage.appdomain.cloud",
        )

    def list_regions(self) -> list[CloudRegionInfo]:
        client = self._vpc_client_for(self.region if self.region and self.region != "all" else "us-south")

        @_ibm_retry
        def _list_regions():
            return client.list_regions()

        try:
            response = _list_regions()
        except ApiException as exc:
            code, message = _classify_ibm_region_error(exc)
            raise ValidationAppError(message, code=code) from exc

        regions = [
            {"id": entry["name"], "display_name": _IBM_REGION_DISPLAY_NAMES.get(entry["name"], entry["name"])}
            for entry in response.get_result().get("regions", [])
        ]
        if not regions:
            raise ValidationAppError(
                "IBM Cloud returned zero regions for this account - unexpected for a working "
                "account, and treated as a failure rather than a legitimately empty result",
                code="IBM_REGION_NO_REGIONS_RETURNED",
            )
        return regions

    def list_projects(self) -> list[str]:
        account_id, _, _ = self._identity()
        return [account_id] if account_id else []

    def _identity(self) -> tuple[str | None, str | None, str | None]:
        # Best-effort only - the base class's test_connection() has already
        # proven the credentials work via a real list_regions() call by the
        # time this runs. IBM's IAM API doesn't expose a friendly "account
        # name" the way Azure/OCI do, so account_alias is honestly None
        # rather than fabricated (same disclosed gap as Alibaba).
        try:
            client = ibm_platform_services.IamIdentityV1(authenticator=self._authenticator())
            result = client.get_api_keys_details(iam_api_key=self.credentials["api_key"]).get_result()
            return result.get("account_id"), None, result.get("name") or result.get("iam_id")
        except ApiException:
            return None, None, None

    def _wrap_api_exception(self, exc: ApiException, code: str) -> ValidationAppError:
        return ValidationAppError(f"IBM Cloud rejected the request ({exc.status_code}): {exc.message}", code=code)

    def list_resources(self, region: str) -> list[CloudResourceSummary]:
        client = self._vpc_client_for(region)

        @_ibm_retry
        def _list_instances():
            return client.list_instances()

        try:
            response = _list_instances()
        except ApiException as exc:
            raise self._wrap_api_exception(exc, "IBM_RESOURCE_INVENTORY_FAILED") from exc

        return [
            {
                "id": instance["id"],
                "name": instance["name"],
                "type": instance.get("profile", {}).get("name", "unknown"),
                "region": region,
                "status": instance.get("status", "unknown"),
                "created_at": instance.get("created_at"),
            }
            for instance in response.get_result().get("instances", [])
        ]

    def _resource_instances_by_service_prefix(self, matches) -> list[dict]:
        client = self._resource_controller_client()

        @_ibm_retry
        def _list_resource_instances():
            return client.list_resource_instances()

        try:
            response = _list_resource_instances()
        except ApiException as exc:
            raise self._wrap_api_exception(exc, "IBM_INVENTORY_FAILED") from exc

        results = []
        for resource in response.get_result().get("resources", []):
            crn_parts = resource.get("crn", "").split(":")
            service_name = crn_parts[4] if len(crn_parts) > 4 else ""
            if matches(service_name):
                results.append((resource, service_name))
        return results

    def list_clusters(self, region: str) -> list[CloudResourceSummary]:
        try:
            matched = self._resource_instances_by_service_prefix(lambda name: name in _KUBERNETES_SERVICE_NAMES)
        except ApiException as exc:
            raise self._wrap_api_exception(exc, "IBM_CLUSTER_INVENTORY_FAILED") from exc

        return [
            {
                "id": resource["id"],
                "name": resource["name"],
                "type": service_name,
                "region": resource.get("region_id", region),
                "status": resource.get("state", "unknown"),
                "created_at": resource.get("created_at"),
            }
            for resource, service_name in matched
            if resource.get("region_id", region) == region
        ]

    def list_databases(self, region: str) -> list[CloudResourceSummary]:
        try:
            matched = self._resource_instances_by_service_prefix(lambda name: name.startswith("databases-for-"))
        except ApiException as exc:
            raise self._wrap_api_exception(exc, "IBM_DATABASE_INVENTORY_FAILED") from exc

        return [
            {
                "id": resource["id"],
                "name": resource["name"],
                "type": service_name,
                "region": resource.get("region_id", region),
                "status": resource.get("state", "unknown"),
                "created_at": resource.get("created_at"),
            }
            for resource, service_name in matched
            if resource.get("region_id", region) == region
        ]

    def list_storage(self, region: str) -> list[CloudResourceSummary]:
        client = self._cos_client(region)
        try:
            response = client.list_buckets()
        except ibm_botocore.exceptions.ClientError as exc:
            raise ValidationAppError(
                f"IBM Cloud Object Storage rejected the storage-inventory request: {exc}",
                code="IBM_STORAGE_INVENTORY_FAILED",
            ) from exc

        return [
            {
                "id": bucket["Name"],
                "name": bucket["Name"],
                "type": "cos_bucket",
                "region": region,
                "status": "available",
                "created_at": bucket.get("CreationDate"),
            }
            for bucket in response.get("Buckets", [])
        ]

    def list_networking(self, region: str) -> list[CloudResourceSummary]:
        client = self._vpc_client_for(region)

        @_ibm_retry
        def _list_vpcs():
            return client.list_vpcs()

        try:
            response = _list_vpcs()
        except ApiException as exc:
            raise self._wrap_api_exception(exc, "IBM_NETWORKING_INVENTORY_FAILED") from exc

        return [
            {
                "id": vpc["id"],
                "name": vpc["name"],
                "type": "vpc",
                "region": region,
                "status": vpc.get("status", "unknown"),
                "created_at": vpc.get("created_at"),
            }
            for vpc in response.get_result().get("vpcs", [])
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
            return self._destroy_compute(region, resource_id)
        if resource_type == "storage":
            return self._destroy_storage(region, resource_id)
        if resource_type == "networking":
            return self._destroy_networking(region, resource_id)
        raise self._not_yet_supported(f"Provisioning of '{resource_type}'")

    @staticmethod
    def _require_spec(spec: dict, keys: tuple[str, ...]) -> None:
        missing = [k for k in keys if not spec.get(k)]
        if missing:
            raise ValidationAppError(
                f"IBM Cloud deploy requires spec.{', spec.'.join(missing)}", code="IBM_DEPLOY_SPEC_INCOMPLETE"
            )

    def _deploy_compute(self, region: str, spec: dict) -> CloudResourceSummary:
        # A real IBM VPC instance needs a VM image, a zone within the
        # target region, and a subnet within an existing VPC - all real,
        # standard IBM VPC prerequisites this platform cannot fabricate on
        # the caller's behalf (the same honest stance as requiring an AMI
        # id for AWS).
        self._require_spec(spec, ("image_id", "zone", "subnet_id", "vpc_id"))
        client = self._vpc_client_for(region)
        name = spec.get("name", "cloud-ai-platform-instance")
        prototype = {
            "name": name,
            "zone": {"name": spec["zone"]},
            "profile": {"name": _DEPLOY_PROFILE},
            "image": {"id": spec["image_id"]},
            "vpc": {"id": spec["vpc_id"]},
            "primary_network_interface": {"subnet": {"id": spec["subnet_id"]}},
        }
        resource_group_id = self.credentials.get("resource_group_id")
        if resource_group_id:
            prototype["resource_group"] = {"id": resource_group_id}
        try:
            response = client.create_instance(prototype)
        except ApiException as exc:
            raise self._wrap_api_exception(exc, "IBM_DEPLOY_FAILED") from exc

        instance = response.get_result()
        return {
            "id": instance["id"],
            "name": instance["name"],
            "type": _DEPLOY_PROFILE,
            "region": region,
            "status": instance.get("status", "unknown"),
            "created_at": instance.get("created_at"),
        }

    def _destroy_compute(self, region: str, resource_id: str) -> None:
        client = self._vpc_client_for(region)
        try:
            client.delete_instance(id=resource_id)
        except ApiException as exc:
            raise self._wrap_api_exception(exc, "IBM_DESTROY_FAILED") from exc

    def _deploy_storage(self, region: str, spec: dict) -> CloudResourceSummary:
        name = spec.get("name")
        if not name:
            raise ValidationAppError(
                "IBM Cloud storage deploy requires spec.name (a globally-unique COS bucket name)",
                code="IBM_DEPLOY_SPEC_INCOMPLETE",
            )
        client = self._cos_client(region)
        try:
            client.create_bucket(
                Bucket=name,
                CreateBucketConfiguration={"LocationConstraint": f"{region}-standard"},
            )
        except ibm_botocore.exceptions.ClientError as exc:
            raise ValidationAppError(
                f"IBM Cloud Object Storage rejected the deploy request: {exc}", code="IBM_DEPLOY_FAILED"
            ) from exc

        return {"id": name, "name": name, "type": "cos_bucket", "region": region, "status": "available", "created_at": None}

    def _destroy_storage(self, region: str, resource_id: str) -> None:
        client = self._cos_client(region)
        try:
            # Requires an already-empty bucket - a real COS precondition
            # this platform does not attempt to bypass by force-emptying it.
            client.delete_bucket(Bucket=resource_id)
        except ibm_botocore.exceptions.ClientError as exc:
            raise ValidationAppError(
                f"IBM Cloud Object Storage rejected the destroy request: {exc}", code="IBM_DESTROY_FAILED"
            ) from exc

    def _deploy_networking(self, region: str, spec: dict) -> CloudResourceSummary:
        client = self._vpc_client_for(region)
        name = spec.get("name", "cloud-ai-platform-vpc")
        kwargs: dict = {"name": name}
        resource_group_id = self.credentials.get("resource_group_id")
        if resource_group_id:
            kwargs["resource_group"] = {"id": resource_group_id}
        try:
            response = client.create_vpc(**kwargs)
        except ApiException as exc:
            raise self._wrap_api_exception(exc, "IBM_DEPLOY_FAILED") from exc

        vpc = response.get_result()
        return {
            "id": vpc["id"],
            "name": vpc["name"],
            "type": "vpc",
            "region": region,
            "status": vpc.get("status", "unknown"),
            "created_at": vpc.get("created_at"),
        }

    def _destroy_networking(self, region: str, resource_id: str) -> None:
        client = self._vpc_client_for(region)
        try:
            client.delete_vpc(id=resource_id)
        except ApiException as exc:
            raise self._wrap_api_exception(exc, "IBM_DESTROY_FAILED") from exc
