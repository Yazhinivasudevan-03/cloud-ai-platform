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
    CloudResourceSummary,
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

# The one, fixed, smallest/free-tier-eligible instance size deploy() will
# ever request - not user-configurable in this pass, to bound real-world
# cost/blast-radius risk from the very first release of provisioning
# (Phase 25D). Users pick their own size once real production usage
# justifies extending this beyond a fixed minimum.
_DEPLOY_INSTANCE_TYPE = "t3.micro"

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

    def _client_kwargs_for(self, region: str) -> dict[str, str]:
        self.authenticate()
        kwargs: dict[str, str] = {
            "region_name": region,
            "aws_access_key_id": self.credentials["access_key_id"],
            "aws_secret_access_key": self.credentials["secret_access_key"],
        }
        session_token = self.credentials.get("session_token")
        if session_token:
            kwargs["aws_session_token"] = session_token
        endpoint_url = self.credentials.get("endpoint_url")
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        return kwargs

    def _wrap_client_error(self, exc: botocore.exceptions.ClientError, code: str) -> ValidationAppError:
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        message = exc.response.get("Error", {}).get("Message", str(exc))
        return ValidationAppError(f"AWS rejected the request ({error_code}): {message}", code=code)

    def list_resources(self, region: str) -> list[CloudResourceSummary]:
        client = boto3.client("ec2", **self._client_kwargs_for(region))
        try:
            paginator = client.get_paginator("describe_instances")
            results: list[CloudResourceSummary] = []
            for page in paginator.paginate():
                for reservation in page.get("Reservations", []):
                    for instance in reservation.get("Instances", []):
                        name = next(
                            (t["Value"] for t in instance.get("Tags", []) if t.get("Key") == "Name"),
                            instance["InstanceId"],
                        )
                        results.append(
                            {
                                "id": instance["InstanceId"],
                                "name": name,
                                "type": instance.get("InstanceType", "unknown"),
                                "region": region,
                                "status": instance.get("State", {}).get("Name", "unknown"),
                                "created_at": instance.get("LaunchTime"),
                            }
                        )
            return results
        except botocore.exceptions.ClientError as exc:
            raise self._wrap_client_error(exc, "AWS_RESOURCE_INVENTORY_FAILED") from exc

    def list_clusters(self, region: str) -> list[CloudResourceSummary]:
        client = boto3.client("eks", **self._client_kwargs_for(region))
        try:
            cluster_names = client.list_clusters().get("clusters", [])
            results: list[CloudResourceSummary] = []
            for name in cluster_names:
                detail = client.describe_cluster(name=name)["cluster"]
                results.append(
                    {
                        "id": detail.get("arn", name),
                        "name": name,
                        "type": "eks",
                        "region": region,
                        "status": detail.get("status", "unknown"),
                        "created_at": detail.get("createdAt"),
                    }
                )
            return results
        except botocore.exceptions.ClientError as exc:
            raise self._wrap_client_error(exc, "AWS_CLUSTER_INVENTORY_FAILED") from exc

    def list_databases(self, region: str) -> list[CloudResourceSummary]:
        client = boto3.client("rds", **self._client_kwargs_for(region))
        try:
            paginator = client.get_paginator("describe_db_instances")
            results: list[CloudResourceSummary] = []
            for page in paginator.paginate():
                for db in page.get("DBInstances", []):
                    results.append(
                        {
                            "id": db["DBInstanceIdentifier"],
                            "name": db["DBInstanceIdentifier"],
                            "type": db.get("Engine", "unknown"),
                            "region": region,
                            "status": db.get("DBInstanceStatus", "unknown"),
                            "created_at": db.get("InstanceCreateTime"),
                        }
                    )
            return results
        except botocore.exceptions.ClientError as exc:
            raise self._wrap_client_error(exc, "AWS_DATABASE_INVENTORY_FAILED") from exc

    def list_storage(self, region: str) -> list[CloudResourceSummary]:
        # S3's ListBuckets is account-wide, not region-scoped - a bucket
        # created in a different region still appears here (a real
        # limitation of the S3 API itself, not something this platform can
        # filter around without one extra get_bucket_location call per
        # bucket). Every bucket is reported once regardless of which
        # region was requested, disclosed honestly rather than silently
        # pretending buckets are partitioned by region.
        client = boto3.client("s3", **self._client_kwargs_for(region))
        try:
            buckets = client.list_buckets().get("Buckets", [])
            return [
                {
                    "id": bucket["Name"],
                    "name": bucket["Name"],
                    "type": "s3_bucket",
                    "region": region,
                    "status": "available",
                    "created_at": bucket.get("CreationDate"),
                }
                for bucket in buckets
            ]
        except botocore.exceptions.ClientError as exc:
            raise self._wrap_client_error(exc, "AWS_STORAGE_INVENTORY_FAILED") from exc

    def list_networking(self, region: str) -> list[CloudResourceSummary]:
        client = boto3.client("ec2", **self._client_kwargs_for(region))
        try:
            paginator = client.get_paginator("describe_vpcs")
            results: list[CloudResourceSummary] = []
            for page in paginator.paginate():
                for vpc in page.get("Vpcs", []):
                    name = next(
                        (t["Value"] for t in vpc.get("Tags", []) if t.get("Key") == "Name"), vpc["VpcId"]
                    )
                    results.append(
                        {
                            "id": vpc["VpcId"],
                            "name": name,
                            "type": "vpc",
                            "region": region,
                            "status": vpc.get("State", "unknown"),
                            "created_at": None,
                        }
                    )
            return results
        except botocore.exceptions.ClientError as exc:
            raise self._wrap_client_error(exc, "AWS_NETWORKING_INVENTORY_FAILED") from exc

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
        image_id = spec.get("image_id")
        if not image_id:
            raise ValidationAppError(
                "AWS compute deploy requires spec.image_id (an AMI ID valid in the target region)",
                code="AWS_DEPLOY_SPEC_INCOMPLETE",
            )
        client = boto3.client("ec2", **self._client_kwargs_for(region))
        name = spec.get("name", "cloud-ai-platform-instance")
        try:
            response = client.run_instances(
                ImageId=image_id,
                InstanceType=_DEPLOY_INSTANCE_TYPE,
                MinCount=1,
                MaxCount=1,
                TagSpecifications=[{"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": name}]}],
            )
        except botocore.exceptions.ClientError as exc:
            raise self._wrap_client_error(exc, "AWS_DEPLOY_FAILED") from exc

        instance = response["Instances"][0]
        return {
            "id": instance["InstanceId"],
            "name": name,
            "type": _DEPLOY_INSTANCE_TYPE,
            "region": region,
            "status": instance.get("State", {}).get("Name", "unknown"),
            "created_at": instance.get("LaunchTime"),
        }

    def _destroy_compute(self, region: str, resource_id: str) -> None:
        client = boto3.client("ec2", **self._client_kwargs_for(region))
        try:
            client.terminate_instances(InstanceIds=[resource_id])
        except botocore.exceptions.ClientError as exc:
            raise self._wrap_client_error(exc, "AWS_DESTROY_FAILED") from exc

    def _deploy_storage(self, region: str, spec: dict) -> CloudResourceSummary:
        name = spec.get("name")
        if not name:
            raise ValidationAppError(
                "AWS storage deploy requires spec.name (a globally-unique S3 bucket name)",
                code="AWS_DEPLOY_SPEC_INCOMPLETE",
            )
        client = boto3.client("s3", **self._client_kwargs_for(region))
        kwargs: dict = {"Bucket": name}
        # us-east-1 is the one region where CreateBucketConfiguration must
        # be omitted entirely - passing it (even with the "correct" region)
        # is rejected by the real S3 API as an invalid location constraint.
        if region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
        try:
            client.create_bucket(**kwargs)
        except botocore.exceptions.ClientError as exc:
            raise self._wrap_client_error(exc, "AWS_DEPLOY_FAILED") from exc

        return {"id": name, "name": name, "type": "s3_bucket", "region": region, "status": "available", "created_at": None}

    def _destroy_storage(self, region: str, resource_id: str) -> None:
        client = boto3.client("s3", **self._client_kwargs_for(region))
        try:
            # delete_bucket requires an already-empty bucket - a real,
            # deliberate AWS safety precondition this platform does not
            # attempt to bypass by force-emptying it first.
            client.delete_bucket(Bucket=resource_id)
        except botocore.exceptions.ClientError as exc:
            raise self._wrap_client_error(exc, "AWS_DESTROY_FAILED") from exc

    def _deploy_networking(self, region: str, spec: dict) -> CloudResourceSummary:
        cidr_block = spec.get("cidr_block", "10.0.0.0/16")
        client = boto3.client("ec2", **self._client_kwargs_for(region))
        name = spec.get("name", "cloud-ai-platform-vpc")
        try:
            response = client.create_vpc(
                CidrBlock=cidr_block,
                TagSpecifications=[{"ResourceType": "vpc", "Tags": [{"Key": "Name", "Value": name}]}],
            )
        except botocore.exceptions.ClientError as exc:
            raise self._wrap_client_error(exc, "AWS_DEPLOY_FAILED") from exc

        vpc = response["Vpc"]
        return {
            "id": vpc["VpcId"],
            "name": name,
            "type": "vpc",
            "region": region,
            "status": vpc.get("State", "unknown"),
            "created_at": None,
        }

    def _destroy_networking(self, region: str, resource_id: str) -> None:
        client = boto3.client("ec2", **self._client_kwargs_for(region))
        try:
            client.delete_vpc(VpcId=resource_id)
        except botocore.exceptions.ClientError as exc:
            raise self._wrap_client_error(exc, "AWS_DESTROY_FAILED") from exc
