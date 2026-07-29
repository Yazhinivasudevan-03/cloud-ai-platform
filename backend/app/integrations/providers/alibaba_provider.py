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
    return False


_alibaba_retry = tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable_alibaba_error),
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
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
            raise ValidationAppError(
                f"Alibaba Cloud rejected the region-discovery request ({exc.code}): {exc.message}",
                code="ALIBABA_REGION_DISCOVERY_FAILED",
            ) from exc

        regions = response.body.regions.region or []
        return [{"id": r.region_id, "display_name": r.local_name or r.region_id} for r in regions]

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
        try:
            response = client.describe_instances(request)
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
        try:
            response = client.describe_clusters_v1(request)
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
        try:
            response = client.describe_dbinstances(request)
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
        try:
            service = oss2.Service(auth, endpoint)
            result = service.list_buckets()
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
        try:
            response = client.describe_vpcs(request)
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
