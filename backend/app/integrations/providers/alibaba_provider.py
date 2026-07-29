"""Alibaba Cloud CloudProviderClient adapter (Phase 25B) - built against the
official Tea-based Alibaba Cloud SDKs (`alibabacloud_ecs20140526` for
region discovery, `alibabacloud_cms20190101` for CloudMonitor metrics),
following the same "one adapter class per provider" shape as
oci_provider.py/aws_provider.py/azure_provider.py/gcp_provider.py.

Honesty note (same disclosed limitation as oci_provider.py): there is no
Alibaba Cloud emulator available and no live account to validate this
against, so this module is verified only against mocked SDK client
responses (see tests/test_alibaba_provider.py), never a real request/
response round trip. CloudMonitor's exact ECS metric names/units
(CPUUtilization/InternetInRate/InternetOutRate, assumed bit/sec per
Alibaba's published metric reference) should be re-verified against a real
account before this integration is pointed at production traffic.

Credentials dict shape: {"access_key_id": "...", "access_key_secret": "..."}
(plain RAM access keys, the same two-field shape AWS's IAM access keys use).

Only CPU utilization and network in/out are available from CloudMonitor's
standard ECS dashboard metrics without the CloudMonitor agent installed -
memory/disk are reported as 0.0, the same disclosed limitation as every
other provider in this platform.
"""
import json
from datetime import datetime, timedelta, timezone
from typing import TypedDict

import oss2
import tenacity
from alibabacloud_cms20190101 import models as cms_models
from alibabacloud_cms20190101.client import Client as CmsClient
from alibabacloud_cs20151215 import models as cs_models
from alibabacloud_cs20151215.client import Client as CsClient
from alibabacloud_ecs20140526 import models as ecs_models
from alibabacloud_ecs20140526.client import Client as EcsClient
from alibabacloud_rds20140815 import models as rds_models
from alibabacloud_rds20140815.client import Client as RdsClient
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_vpc20160428 import models as vpc_models
from alibabacloud_vpc20160428.client import Client as VpcClient
from Tea.exceptions import TeaException

from app.integrations.cloud_provider_client import CloudProviderClient, CloudRegionInfo, CloudResourceSummary
from app.utils.exceptions import ValidationAppError

_CMS_NAMESPACE = "acs_ecs_dashboard"
_DEFAULT_REGION = "cn-hangzhou"

# The one, fixed, smallest/free-tier-eligible instance type deploy() will
# ever request - not user-configurable in this pass (see aws_provider.py's
# identical _DEPLOY_INSTANCE_TYPE for the same reasoning).
_DEPLOY_INSTANCE_TYPE = "ecs.t5-lc1m1.small"


class InstanceResourceUsage(TypedDict):
    cpu_usage_percent: float
    memory_usage_mb: float
    disk_usage_mb: float
    network_in_kbps: float
    network_out_kbps: float
    recorded_at: datetime


def _parse_alibaba_timestamp(value) -> datetime | None:
    """Alibaba's Tea SDKs return timestamps as ISO-8601 strings - Python
    3.11+'s fromisoformat handles the trailing 'Z' UTC suffix directly."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _is_retryable_alibaba_error(exc: BaseException) -> bool:
    if isinstance(exc, TeaException):
        code = str(getattr(exc, "code", ""))
        return code in ("Throttling", "ServiceUnavailable", "InternalError")
    # OSS (list_storage/deploy_storage) goes through oss2, not the Tea-based
    # clients - same transient-status codes, different exception type.
    if isinstance(exc, oss2.exceptions.OssError):
        return exc.status in (429, 500, 503)
    return False


_alibaba_retry = tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable_alibaba_error),
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)

_ALIBABA_CREDENTIALS_CODES = {
    "InvalidAccessKeyId.NotFound",
    "IncompleteSignature",
    "SignatureDoesNotMatch",
    "InvalidSecurityToken.Expired",
}
_ALIBABA_ACCESS_DENIED_CODES = {"Forbidden.RAM", "NoPermission", "Forbidden"}
_ALIBABA_OUTAGE_CODES = {"ServiceUnavailable", "InternalError"}


# Phase 25E: region-discovery error taxonomy (see aws_provider.py's
# identical rationale) - Alibaba's TeaException.code is a real Alibaba
# Cloud API error code (e.g. "Throttling", "Forbidden.RAM"), so these
# categories read directly from it rather than guessing.
def _classify_alibaba_region_error(exc: TeaException) -> tuple[str, str]:
    error_code = str(getattr(exc, "code", ""))
    message = str(getattr(exc, "message", exc))
    if error_code == "InvalidSecurityToken.Expired":
        return "ALIBABA_REGION_CREDENTIALS_EXPIRED", f"Alibaba Cloud credentials have expired: {message}"
    if error_code in _ALIBABA_CREDENTIALS_CODES:
        return "ALIBABA_REGION_CREDENTIALS_REJECTED", f"Alibaba Cloud rejected the credentials: {message}"
    if error_code in _ALIBABA_ACCESS_DENIED_CODES:
        return "ALIBABA_REGION_ACCESS_DENIED", f"Alibaba Cloud denied access to the region-discovery request: {message}"
    if error_code == "Throttling":
        return (
            "ALIBABA_REGION_THROTTLED",
            f"Alibaba Cloud throttled the region-discovery request even after retries: {message}",
        )
    if error_code in _ALIBABA_OUTAGE_CODES:
        return "ALIBABA_REGION_PROVIDER_OUTAGE", f"Alibaba Cloud reported a service outage: {message}"
    return (
        "ALIBABA_REGION_DISCOVERY_FAILED",
        f"Alibaba Cloud rejected the region-discovery request ({error_code}): {message}",
    )


class AlibabaCloudProviderClient(CloudProviderClient):
    @property
    def provider_name(self) -> str:
        return "alibaba"

    def authenticate(self) -> None:
        if not self.credentials.get("access_key_id") or not self.credentials.get("access_key_secret"):
            raise ValidationAppError(
                "Alibaba Cloud credentials must include 'access_key_id' and 'access_key_secret'",
                code="ALIBABA_CREDENTIALS_INCOMPLETE",
            )

    def _region(self) -> str:
        return self.region if self.region and self.region != "all" else _DEFAULT_REGION

    def _ecs_client(self) -> EcsClient:
        self.authenticate()
        region = self._region()
        config = open_api_models.Config(
            access_key_id=self.credentials["access_key_id"],
            access_key_secret=self.credentials["access_key_secret"],
            region_id=region,
        )
        config.endpoint = f"ecs.{region}.aliyuncs.com"
        return EcsClient(config)

    def _cms_client(self) -> CmsClient:
        self.authenticate()
        region = self._region()
        config = open_api_models.Config(
            access_key_id=self.credentials["access_key_id"],
            access_key_secret=self.credentials["access_key_secret"],
            region_id=region,
        )
        config.endpoint = f"metrics.{region}.aliyuncs.com"
        return CmsClient(config)

    def _config_for(self, region: str) -> open_api_models.Config:
        self.authenticate()
        return open_api_models.Config(
            access_key_id=self.credentials["access_key_id"],
            access_key_secret=self.credentials["access_key_secret"],
            region_id=region,
        )

    def _ecs_client_for(self, region: str) -> EcsClient:
        config = self._config_for(region)
        config.endpoint = f"ecs.{region}.aliyuncs.com"
        return EcsClient(config)

    def _wrap_tea_exception(self, exc: TeaException, code: str) -> ValidationAppError:
        return ValidationAppError(
            f"Alibaba Cloud rejected the request ({exc.code}): {exc.message}", code=code
        )

    def list_regions(self) -> list[CloudRegionInfo]:
        client = self._ecs_client()
        # accept_language="en-US" asks Alibaba's own API for an English
        # display name (local_name) directly - unlike AWS/GCP/OCI, no
        # curated lookup table is needed here.
        request = ecs_models.DescribeRegionsRequest(accept_language="en-US")

        @_alibaba_retry
        def _describe_regions():
            return client.describe_regions(request)

        try:
            response = _describe_regions()
        except TeaException as exc:
            code, message = _classify_alibaba_region_error(exc)
            raise ValidationAppError(message, code=code) from exc

        regions = response.body.regions.region or []
        results = [{"id": r.region_id, "display_name": r.local_name or r.region_id} for r in regions]
        if not results:
            raise ValidationAppError(
                "Alibaba Cloud returned zero regions for this account - unexpected for a working "
                "account, and treated as a failure rather than a legitimately empty result",
                code="ALIBABA_REGION_NO_REGIONS_RETURNED",
            )
        return results

    def list_monitoring(self, resource_id: str, lookback_minutes: int) -> InstanceResourceUsage:
        client = self._cms_client()
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=lookback_minutes)

        def _query(metric_name: str) -> float | None:
            request = cms_models.DescribeMetricLastRequest(
                namespace=_CMS_NAMESPACE,
                metric_name=metric_name,
                dimensions=json.dumps([{"instanceId": resource_id}]),
                start_time=start_time.strftime("%Y-%m-%d %H:%M:%S"),
                end_time=end_time.strftime("%Y-%m-%d %H:%M:%S"),
            )

            @_alibaba_retry
            def _describe_metric_last():
                return client.describe_metric_last(request)

            try:
                response = _describe_metric_last()
            except TeaException as exc:
                raise ValidationAppError(
                    f"Alibaba CloudMonitor rejected the request ({exc.code}): {exc.message}",
                    code="ALIBABA_MONITORING_REQUEST_FAILED",
                ) from exc

            # CloudMonitor's DescribeMetricLast returns Datapoints as a
            # JSON-encoded string field, not a nested object - a real,
            # documented quirk of this API, not a parsing shortcut.
            raw_datapoints = response.body.datapoints
            if not raw_datapoints:
                return None
            datapoints = json.loads(raw_datapoints)
            if not datapoints:
                return None
            return datapoints[-1].get("Average") or datapoints[-1].get("average")

        cpu = _query("CPUUtilization")
        network_in = _query("InternetInRate")
        network_out = _query("InternetOutRate")

        if cpu is None and network_in is None and network_out is None:
            raise ValidationAppError(
                f"Alibaba CloudMonitor returned no datapoints for instance '{resource_id}' "
                f"in the last {lookback_minutes} minutes",
                code="NO_ALIBABA_MONITORING_DATA",
            )

        # InternetInRate/InternetOutRate are published in bit/s already
        # (per Alibaba's ECS CloudMonitor metric reference) - dividing by
        # 1000 converts straight to kbps, no bytes-to-bits step needed
        # (unlike AWS/Azure/GCP's byte-denominated network metrics).
        return {
            "cpu_usage_percent": cpu or 0.0,
            "memory_usage_mb": 0.0,
            "disk_usage_mb": 0.0,
            "network_in_kbps": (network_in or 0.0) / 1000,
            "network_out_kbps": (network_out or 0.0) / 1000,
            "recorded_at": end_time,
        }

    def list_resources(self, region: str) -> list[CloudResourceSummary]:
        client = self._ecs_client_for(region)
        request = ecs_models.DescribeInstancesRequest(region_id=region)

        @_alibaba_retry
        def _describe_instances():
            return client.describe_instances(request)

        try:
            response = _describe_instances()
        except TeaException as exc:
            raise self._wrap_tea_exception(exc, "ALIBABA_RESOURCE_INVENTORY_FAILED") from exc

        instances = response.body.instances.instance or []
        return [
            {
                "id": instance.instance_id,
                "name": instance.instance_name or instance.instance_id,
                "type": instance.instance_type,
                "region": region,
                "status": instance.status,
                "created_at": _parse_alibaba_timestamp(instance.creation_time),
            }
            for instance in instances
        ]

    def list_clusters(self, region: str) -> list[CloudResourceSummary]:
        config = self._config_for(region)
        config.endpoint = f"cs.{region}.aliyuncs.com"
        client = CsClient(config)
        request = cs_models.DescribeClustersV1Request(region_id=region)

        @_alibaba_retry
        def _describe_clusters():
            return client.describe_clusters_v1(request)

        try:
            response = _describe_clusters()
        except TeaException as exc:
            raise self._wrap_tea_exception(exc, "ALIBABA_CLUSTER_INVENTORY_FAILED") from exc

        clusters = response.body.clusters or []
        return [
            {
                "id": cluster.cluster_id,
                "name": cluster.name or cluster.cluster_id,
                "type": cluster.cluster_type or "ack",
                "region": region,
                "status": cluster.state,
                "created_at": _parse_alibaba_timestamp(cluster.created),
            }
            for cluster in clusters
        ]

    def list_databases(self, region: str) -> list[CloudResourceSummary]:
        config = self._config_for(region)
        config.endpoint = f"rds.{region}.aliyuncs.com"
        client = RdsClient(config)
        request = rds_models.DescribeDBInstancesRequest(region_id=region)

        @_alibaba_retry
        def _describe_dbinstances():
            return client.describe_dbinstances(request)

        try:
            response = _describe_dbinstances()
        except TeaException as exc:
            raise self._wrap_tea_exception(exc, "ALIBABA_DATABASE_INVENTORY_FAILED") from exc

        instances = response.body.items.dbinstance or []
        return [
            {
                "id": db.dbinstance_id,
                "name": db.dbinstance_description or db.dbinstance_id,
                "type": db.engine,
                "region": region,
                "status": db.dbinstance_status,
                "created_at": _parse_alibaba_timestamp(db.create_time),
            }
            for db in instances
        ]

    def list_storage(self, region: str) -> list[CloudResourceSummary]:
        self.authenticate()
        auth = oss2.Auth(self.credentials["access_key_id"], self.credentials["access_key_secret"])
        endpoint = f"https://oss-{region}.aliyuncs.com"

        @_alibaba_retry
        def _list_buckets():
            return oss2.Service(auth, endpoint).list_buckets()

        try:
            result = _list_buckets()
        except oss2.exceptions.OssError as exc:
            raise ValidationAppError(
                f"Alibaba OSS rejected the storage-inventory request: {exc}",
                code="ALIBABA_STORAGE_INVENTORY_FAILED",
            ) from exc

        return [
            {
                "id": bucket.name,
                "name": bucket.name,
                "type": "oss_bucket",
                "region": region,
                "status": "available",
                "created_at": _parse_alibaba_timestamp(bucket.creation_date),
            }
            for bucket in result.buckets
        ]

    def list_networking(self, region: str) -> list[CloudResourceSummary]:
        config = self._config_for(region)
        config.endpoint = f"vpc.{region}.aliyuncs.com"
        client = VpcClient(config)
        request = vpc_models.DescribeVpcsRequest(region_id=region)

        @_alibaba_retry
        def _describe_vpcs():
            return client.describe_vpcs(request)

        try:
            response = _describe_vpcs()
        except TeaException as exc:
            raise self._wrap_tea_exception(exc, "ALIBABA_NETWORKING_INVENTORY_FAILED") from exc

        vpcs = response.body.vpcs.vpc or []
        return [
            {
                "id": vpc.vpc_id,
                "name": vpc.vpc_name or vpc.vpc_id,
                "type": "vpc",
                "region": region,
                "status": vpc.status,
                "created_at": _parse_alibaba_timestamp(vpc.creation_time),
            }
            for vpc in vpcs
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

    def _deploy_compute(self, region: str, spec: dict) -> CloudResourceSummary:
        # A real ECS instance needs an image and a security group - both
        # real, standard Alibaba Cloud prerequisites this platform cannot
        # fabricate on the caller's behalf (the same honest stance as
        # requiring an AMI id for AWS).
        image_id = spec.get("image_id")
        security_group_id = spec.get("security_group_id")
        if not image_id or not security_group_id:
            raise ValidationAppError(
                "Alibaba compute deploy requires spec.image_id and spec.security_group_id",
                code="ALIBABA_DEPLOY_SPEC_INCOMPLETE",
            )
        client = self._ecs_client_for(region)
        name = spec.get("name", "cloud-ai-platform-instance")
        request = ecs_models.CreateInstanceRequest(
            region_id=region,
            image_id=image_id,
            instance_type=_DEPLOY_INSTANCE_TYPE,
            security_group_id=security_group_id,
            instance_name=name,
        )
        try:
            response = client.create_instance(request)
        except TeaException as exc:
            raise self._wrap_tea_exception(exc, "ALIBABA_DEPLOY_FAILED") from exc

        instance_id = response.body.instance_id
        return {
            "id": instance_id,
            "name": name,
            "type": _DEPLOY_INSTANCE_TYPE,
            "region": region,
            "status": "Pending",
            "created_at": None,
        }

    def _destroy_compute(self, region: str, resource_id: str) -> None:
        client = self._ecs_client_for(region)
        request = ecs_models.DeleteInstanceRequest(instance_id=resource_id, force=True)
        try:
            client.delete_instance(request)
        except TeaException as exc:
            raise self._wrap_tea_exception(exc, "ALIBABA_DESTROY_FAILED") from exc

    def _oss_bucket(self, region: str, name: str) -> "oss2.Bucket":
        self.authenticate()
        auth = oss2.Auth(self.credentials["access_key_id"], self.credentials["access_key_secret"])
        endpoint = f"https://oss-{region}.aliyuncs.com"
        return oss2.Bucket(auth, endpoint, name)

    def _deploy_storage(self, region: str, spec: dict) -> CloudResourceSummary:
        name = spec.get("name")
        if not name:
            raise ValidationAppError(
                "Alibaba storage deploy requires spec.name (a globally-unique OSS bucket name)",
                code="ALIBABA_DEPLOY_SPEC_INCOMPLETE",
            )
        try:
            self._oss_bucket(region, name).create_bucket()
        except oss2.exceptions.OssError as exc:
            raise ValidationAppError(
                f"Alibaba OSS rejected the deploy request: {exc}", code="ALIBABA_DEPLOY_FAILED"
            ) from exc

        return {"id": name, "name": name, "type": "oss_bucket", "region": region, "status": "available", "created_at": None}

    def _destroy_storage(self, region: str, resource_id: str) -> None:
        try:
            # Requires an already-empty bucket - a real OSS precondition
            # this platform does not attempt to bypass by force-emptying it.
            self._oss_bucket(region, resource_id).delete_bucket()
        except oss2.exceptions.OssError as exc:
            raise ValidationAppError(
                f"Alibaba OSS rejected the destroy request: {exc}", code="ALIBABA_DESTROY_FAILED"
            ) from exc

    def _deploy_networking(self, region: str, spec: dict) -> CloudResourceSummary:
        cidr_block = spec.get("cidr_block", "10.0.0.0/16")
        name = spec.get("name", "cloud-ai-platform-vpc")
        config = self._config_for(region)
        config.endpoint = f"vpc.{region}.aliyuncs.com"
        client = VpcClient(config)
        request = vpc_models.CreateVpcRequest(region_id=region, cidr_block=cidr_block, vpc_name=name)
        try:
            response = client.create_vpc(request)
        except TeaException as exc:
            raise self._wrap_tea_exception(exc, "ALIBABA_DEPLOY_FAILED") from exc

        vpc_id = response.body.vpc_id
        return {"id": vpc_id, "name": name, "type": "vpc", "region": region, "status": "Pending", "created_at": None}

    def _destroy_networking(self, region: str, resource_id: str) -> None:
        config = self._config_for(region)
        config.endpoint = f"vpc.{region}.aliyuncs.com"
        client = VpcClient(config)
        request = vpc_models.DeleteVpcRequest(vpc_id=resource_id)
        try:
            client.delete_vpc(request)
        except TeaException as exc:
            raise self._wrap_tea_exception(exc, "ALIBABA_DESTROY_FAILED") from exc
