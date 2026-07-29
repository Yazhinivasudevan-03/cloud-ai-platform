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

import tenacity
from alibabacloud_cms20190101 import models as cms_models
from alibabacloud_cms20190101.client import Client as CmsClient
from alibabacloud_ecs20140526 import models as ecs_models
from alibabacloud_ecs20140526.client import Client as EcsClient
from alibabacloud_tea_openapi import models as open_api_models
from Tea.exceptions import TeaException

from app.integrations.cloud_provider_client import CloudProviderClient, CloudRegionInfo
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
