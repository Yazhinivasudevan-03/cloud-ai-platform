"""AWS CloudProviderClient adapter (Phase 25) - wraps the existing, already
real AWS fetcher functions (app/integrations/aws_cloudwatch.py,
aws_cost_explorer.py) for list_monitoring/list_costs, and adds a genuinely
new real call for list_regions/list_projects: EC2's DescribeRegions and
STS's GetCallerIdentity. No region list is ever hardcoded - describe_regions()
is a live call every time (refresh_regions() and list_regions() are
identical for this reason; caching is CloudRegionSyncService's job, not
this adapter's).
"""
from datetime import datetime, timezone

import boto3
import botocore.exceptions
import tenacity

from app.integrations.aws_cloudwatch import fetch_ec2_resource_usage
from app.integrations.aws_cost_explorer import fetch_monthly_costs_by_service
from app.integrations.cloud_provider_client import (
    CloudProviderClient,
    CloudRegionInfo,
    MonthlyServiceCost,
    ResourceUsageSnapshot,
)
from app.utils.exceptions import ValidationAppError

# AWS's DescribeRegions API returns only region codes (e.g. "us-east-1"),
# never a human-readable display name - this table is presentation-only
# labelling for regions the live API actually returned, not a substitute
# for calling it. An unmapped/newly-launched region still appears (using
# its raw code as the display name via .get(..., region_id) below), it's
# simply not yet prettified - it is never hidden.
_AWS_REGION_DISPLAY_NAMES = {
    "us-east-1": "US East (N. Virginia)",
    "us-east-2": "US East (Ohio)",
    "us-west-1": "US West (N. California)",
    "us-west-2": "US West (Oregon)",
    "eu-west-1": "Europe (Ireland)",
    "eu-west-2": "Europe (London)",
    "eu-west-3": "Europe (Paris)",
    "eu-central-1": "Europe (Frankfurt)",
    "eu-north-1": "Europe (Stockholm)",
    "ap-south-1": "Asia Pacific (Mumbai)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-southeast-2": "Asia Pacific (Sydney)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ap-northeast-2": "Asia Pacific (Seoul)",
    "ca-central-1": "Canada (Central)",
    "sa-east-1": "South America (Sao Paulo)",
}

_RETRYABLE_CLIENT_ERROR_CODES = {
    "Throttling",
    "ThrottlingException",
    "RequestLimitExceeded",
    "TooManyRequestsException",
    "ServiceUnavailable",
    "InternalError",
    "RequestTimeout",
}


def _is_retryable_aws_error(exc: BaseException) -> bool:
    if isinstance(exc, botocore.exceptions.ClientError):
        return exc.response.get("Error", {}).get("Code") in _RETRYABLE_CLIENT_ERROR_CODES
    return isinstance(exc, botocore.exceptions.BotoCoreError)


_aws_retry = tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable_aws_error),
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)


class AwsCloudProviderClient(CloudProviderClient):
    @property
    def provider_name(self) -> str:
        return "aws"

    def authenticate(self) -> None:
        if not self.credentials.get("access_key_id") or not self.credentials.get("secret_access_key"):
            raise ValidationAppError(
                "AWS credentials must include 'access_key_id' and 'secret_access_key'",
                code="AWS_CREDENTIALS_INCOMPLETE",
            )

    def _client_kwargs(self) -> dict[str, str]:
        self.authenticate()
        kwargs: dict[str, str] = {
            "region_name": self.region if self.region and self.region != "all" else "us-east-1",
            "aws_access_key_id": self.credentials["access_key_id"],
            "aws_secret_access_key": self.credentials["secret_access_key"],
        }
        session_token = self.credentials.get("session_token")
        if session_token:
            kwargs["aws_session_token"] = session_token
        # Only ever set for testing against a real API-compatible emulator
        # (moto) - a genuine AWS account never needs this.
        endpoint_url = self.credentials.get("endpoint_url")
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        return kwargs

    def list_regions(self) -> list[CloudRegionInfo]:
        client = boto3.client("ec2", **self._client_kwargs())

        @_aws_retry
        def _describe_regions():
            return client.describe_regions(AllRegions=False)

        try:
            response = _describe_regions()
        except botocore.exceptions.ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            raise ValidationAppError(
                f"AWS rejected the region-discovery request ({error_code}): "
                f"{exc.response.get('Error', {}).get('Message', str(exc))}",
                code="AWS_REGION_DISCOVERY_FAILED",
            ) from exc
        except botocore.exceptions.BotoCoreError as exc:
            raise ValidationAppError(
                f"Could not reach AWS to discover regions: {exc}", code="AWS_REGION_DISCOVERY_FAILED"
            ) from exc

        return [
            {
                "id": entry["RegionName"],
                "display_name": _AWS_REGION_DISPLAY_NAMES.get(entry["RegionName"], entry["RegionName"]),
            }
            for entry in response.get("Regions", [])
        ]

    def list_projects(self) -> list[str]:
        client = boto3.client("sts", **self._client_kwargs())
        try:
            identity = client.get_caller_identity()
        except botocore.exceptions.ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            raise ValidationAppError(
                f"AWS rejected the account-identity request ({error_code})",
                code="AWS_IDENTITY_REQUEST_FAILED",
            ) from exc
        return [identity["Account"]]

    def list_monitoring(self, resource_id: str, lookback_minutes: int) -> ResourceUsageSnapshot:
        return fetch_ec2_resource_usage(self.credentials, self.region, resource_id, lookback_minutes)  # type: ignore[return-value]

    def list_costs(self, months: int) -> list[MonthlyServiceCost]:
        return fetch_monthly_costs_by_service(self.credentials, months)
