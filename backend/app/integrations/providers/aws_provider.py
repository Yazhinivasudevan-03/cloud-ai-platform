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
    ConnectionTestResult,
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

# Phase 25E: a richer error taxonomy for region discovery specifically -
# every category below is a real distinction AWS's own Error.Code exposes
# (never a fabricated guess). Resource-inventory/deploy/destroy paths keep
# their existing single code-per-operation (e.g. AWS_DEPLOY_FAILED) since
# that already identifies which operation failed; region discovery is the
# one path this platform calls most often (every account, every TTL cycle)
# and so is worth the extra classification detail.
_AWS_CREDENTIALS_EXPIRED_CODES = {"ExpiredToken", "ExpiredTokenException", "RequestExpired"}
_AWS_CREDENTIALS_REJECTED_CODES = {"AuthFailure", "SignatureDoesNotMatch", "InvalidClientTokenId"}
_AWS_ACCESS_DENIED_CODES = {"UnauthorizedOperation", "AccessDenied", "AccessDeniedException"}
_AWS_THROTTLING_CODES = {"Throttling", "ThrottlingException", "RequestLimitExceeded", "TooManyRequestsException"}
_AWS_OUTAGE_CODES = {"ServiceUnavailable", "InternalError"}


def _classify_aws_region_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, botocore.exceptions.ClientError):
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        message = exc.response.get("Error", {}).get("Message", str(exc))
        if error_code in _AWS_CREDENTIALS_EXPIRED_CODES:
            return "AWS_REGION_CREDENTIALS_EXPIRED", f"AWS credentials have expired: {message}"
        if error_code in _AWS_CREDENTIALS_REJECTED_CODES:
            return "AWS_REGION_CREDENTIALS_REJECTED", f"AWS rejected the credentials: {message}"
        if error_code in _AWS_ACCESS_DENIED_CODES:
            return "AWS_REGION_ACCESS_DENIED", f"AWS denied access to the region-discovery request: {message}"
        if error_code in _AWS_THROTTLING_CODES:
            return (
                "AWS_REGION_THROTTLED",
                f"AWS throttled the region-discovery request even after retries: {message}",
            )
        if error_code in _AWS_OUTAGE_CODES:
            return "AWS_REGION_PROVIDER_OUTAGE", f"AWS reported a service outage: {message}"
        return "AWS_REGION_DISCOVERY_FAILED", f"AWS rejected the region-discovery request ({error_code}): {message}"
    if isinstance(exc, (botocore.exceptions.ConnectTimeoutError, botocore.exceptions.ReadTimeoutError)):
        return "AWS_REGION_TIMEOUT", f"Timed out reaching AWS to discover regions: {exc}"
    return "AWS_REGION_NETWORK_UNREACHABLE", f"Could not reach AWS to discover regions: {exc}"


# Phase 26: the Cloud Credential Configuration workflow's "Test Connection"
# step validates a *credential pair itself* (STS GetCallerIdentity), a
# different failure surface than region discovery - AWS's real Error.Code
# distinguishes a bad access key from a bad secret key from a valid-but-
# unauthorized pair, so the "Test Connection" UI can show the user the
# exact reason rather than one generic message.
_AWS_SESSION_TOKEN_EXPIRED_CODES = {"ExpiredToken", "ExpiredTokenException", "RequestExpired"}


def _classify_aws_credential_test_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, botocore.exceptions.ClientError):
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        message = exc.response.get("Error", {}).get("Message", str(exc))
        if error_code == "InvalidClientTokenId":
            return "AWS_INVALID_ACCESS_KEY", "The AWS Access Key ID provided does not exist or is invalid."
        if error_code == "SignatureDoesNotMatch":
            return "AWS_INVALID_SECRET_KEY", "The AWS Secret Access Key provided is incorrect."
        if error_code in _AWS_SESSION_TOKEN_EXPIRED_CODES:
            return "AWS_SESSION_TOKEN_EXPIRED", "The provided AWS session token has expired."
        if error_code in _AWS_ACCESS_DENIED_CODES:
            return (
                "AWS_ACCESS_DENIED",
                "Access denied - this credential pair is valid but lacks permission to verify its own "
                "identity (sts:GetCallerIdentity).",
            )
        return "AWS_CREDENTIAL_TEST_FAILED", f"AWS rejected the credentials ({error_code}): {message}"
    return "AWS_NETWORK_ERROR", f"Could not reach AWS - check your network connection ({exc})"


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
        except (botocore.exceptions.ClientError, botocore.exceptions.BotoCoreError) as exc:
            code, message = _classify_aws_region_error(exc)
            raise ValidationAppError(message, code=code) from exc

        regions = [
            {
                "id": entry["RegionName"],
                "display_name": _AWS_REGION_DISPLAY_NAMES.get(entry["RegionName"], entry["RegionName"]),
            }
            for entry in response.get("Regions", [])
        ]
        if not regions:
            raise ValidationAppError(
                "AWS returned zero regions for this account - unexpected for a working AWS account, "
                "and treated as a failure rather than a legitimately empty result",
                code="AWS_REGION_NO_REGIONS_RETURNED",
            )
        return regions

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

    def test_connection(self) -> ConnectionTestResult:
        """The Cloud Credential Configuration workflow's "Test Connection"
        step - a real, live STS GetCallerIdentity call (the specific
        mechanism requested for AWS), then a real region-validity check
        against a live DescribeRegions call. Never persists anything -
        purely a read."""
        self.authenticate()
        sts_client = boto3.client("sts", **self._client_kwargs())
        try:
            identity = sts_client.get_caller_identity()
        except (botocore.exceptions.ClientError, botocore.exceptions.BotoCoreError) as exc:
            code, message = _classify_aws_credential_test_error(exc)
            raise ValidationAppError(message, code=code) from exc

        region = self.region if self.region and self.region != "all" else "us-east-1"
        # Deliberately queried from the stable "us-east-1" endpoint, not
        # self.region - DescribeRegions is the authoritative list of every
        # valid region, so the client fetching it must not itself be scoped
        # to a possibly-invalid target region (which would fail to even
        # construct a request before this validity check could run).
        ec2_client = boto3.client("ec2", **self._client_kwargs_for("us-east-1"))
        try:
            response = ec2_client.describe_regions(AllRegions=False)
        except (botocore.exceptions.ClientError, botocore.exceptions.BotoCoreError) as exc:
            code, message = _classify_aws_region_error(exc)
            raise ValidationAppError(message, code=code) from exc
        region_ids = {entry["RegionName"] for entry in response.get("Regions", [])}
        if self.region != "all" and self.region not in region_ids:
            raise ValidationAppError(
                f"'{self.region}' is not a recognized AWS region.", code="AWS_REGION_INVALID"
            )

        # Best-effort only - a typical least-privilege IAM user has no
        # iam:ListAccountAliases permission at all, and that must never
        # fail an otherwise-successful connection test.
        account_alias = None
        try:
            iam_client = boto3.client("iam", **self._client_kwargs())
            aliases = iam_client.list_account_aliases().get("AccountAliases", [])
            account_alias = aliases[0] if aliases else None
        except (botocore.exceptions.ClientError, botocore.exceptions.BotoCoreError):
            pass

        return {
            "provider": "aws",
            "account_id": identity["Account"],
            "account_alias": account_alias,
            "principal": identity["Arn"],
            "region": region,
            "status": "success",
        }

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

    def _describe_ec2_instances_full(self, region: str) -> list[dict]:
        """Raw per-instance dicts from a single real describe_instances call -
        list_resources() and list_ec2_instances_detailed() (Phase 29) are two
        different projections of this one call, so there is exactly one
        place that ever talks to EC2 for instance inventory."""
        client = boto3.client("ec2", **self._client_kwargs_for(region))

        @_aws_retry
        def _describe_instances() -> list[dict]:
            return list(client.get_paginator("describe_instances").paginate())

        try:
            instances: list[dict] = []
            for page in _describe_instances():
                for reservation in page.get("Reservations", []):
                    instances.extend(reservation.get("Instances", []))
            return instances
        except botocore.exceptions.ClientError as exc:
            raise self._wrap_client_error(exc, "AWS_RESOURCE_INVENTORY_FAILED") from exc

    @staticmethod
    def _ec2_instance_name(instance: dict) -> str:
        return next(
            (t["Value"] for t in instance.get("Tags", []) if t.get("Key") == "Name"),
            instance["InstanceId"],
        )

    def list_resources(self, region: str) -> list[CloudResourceSummary]:
        return [
            {
                "id": instance["InstanceId"],
                "name": self._ec2_instance_name(instance),
                "type": instance.get("InstanceType", "unknown"),
                "region": region,
                "status": instance.get("State", {}).get("Name", "unknown"),
                "created_at": instance.get("LaunchTime"),
            }
            for instance in self._describe_ec2_instances_full(region)
        ]

    def list_ec2_instances_detailed(self, region: str) -> list[dict]:
        """The richer EC2 shape Phase 29's automatic-discovery/dashboard
        pipeline needs (availability_zone, public_ip, private_ip, tags) -
        see CloudProviderClient.list_ec2_instances_detailed's docstring."""
        results: list[dict] = []
        for instance in self._describe_ec2_instances_full(region):
            results.append(
                {
                    "id": instance["InstanceId"],
                    "name": self._ec2_instance_name(instance),
                    "instance_type": instance.get("InstanceType", "unknown"),
                    "region": region,
                    "availability_zone": instance.get("Placement", {}).get("AvailabilityZone"),
                    "status": instance.get("State", {}).get("Name", "unknown"),
                    "public_ip": instance.get("PublicIpAddress"),
                    "private_ip": instance.get("PrivateIpAddress"),
                    "tags": {t["Key"]: t["Value"] for t in instance.get("Tags", []) if "Key" in t},
                    "created_at": instance.get("LaunchTime"),
                }
            )
        return results

    def list_ecs_clusters(self, region: str) -> list[CloudResourceSummary]:
        client = boto3.client("ecs", **self._client_kwargs_for(region))

        @_aws_retry
        def _list_cluster_arns() -> list[str]:
            return client.list_clusters().get("clusterArns", [])

        @_aws_retry
        def _describe_clusters(arns: list[str]) -> list[dict]:
            return client.describe_clusters(clusters=arns).get("clusters", [])

        try:
            arns = _list_cluster_arns()
            if not arns:
                return []
            return [
                {
                    "id": cluster["clusterArn"],
                    "name": cluster.get("clusterName", cluster["clusterArn"]),
                    "type": "ecs_cluster",
                    "region": region,
                    "status": cluster.get("status", "unknown"),
                    "created_at": None,
                }
                for cluster in _describe_clusters(arns)
            ]
        except botocore.exceptions.ClientError as exc:
            raise self._wrap_client_error(exc, "AWS_ECS_INVENTORY_FAILED") from exc

    def list_serverless_functions(self, region: str) -> list[CloudResourceSummary]:
        client = boto3.client("lambda", **self._client_kwargs_for(region))

        @_aws_retry
        def _list_functions() -> list[dict]:
            return list(client.get_paginator("list_functions").paginate())

        try:
            results: list[CloudResourceSummary] = []
            for page in _list_functions():
                for fn in page.get("Functions", []):
                    results.append(
                        {
                            "id": fn["FunctionArn"],
                            "name": fn["FunctionName"],
                            "type": fn.get("Runtime", "unknown"),
                            "region": region,
                            "status": fn.get("State", "Active"),
                            "created_at": None,
                        }
                    )
            return results
        except botocore.exceptions.ClientError as exc:
            raise self._wrap_client_error(exc, "AWS_LAMBDA_INVENTORY_FAILED") from exc

    def list_volumes(self, region: str) -> list[CloudResourceSummary]:
        client = boto3.client("ec2", **self._client_kwargs_for(region))

        @_aws_retry
        def _describe_volumes() -> list[dict]:
            return list(client.get_paginator("describe_volumes").paginate())

        try:
            results: list[CloudResourceSummary] = []
            for page in _describe_volumes():
                for volume in page.get("Volumes", []):
                    name = next(
                        (t["Value"] for t in volume.get("Tags", []) if t.get("Key") == "Name"),
                        volume["VolumeId"],
                    )
                    results.append(
                        {
                            "id": volume["VolumeId"],
                            "name": name,
                            "type": volume.get("VolumeType", "unknown"),
                            "region": region,
                            "status": volume.get("State", "unknown"),
                            "created_at": volume.get("CreateTime"),
                        }
                    )
            return results
        except botocore.exceptions.ClientError as exc:
            raise self._wrap_client_error(exc, "AWS_VOLUME_INVENTORY_FAILED") from exc

    def list_load_balancers(self, region: str) -> list[CloudResourceSummary]:
        client = boto3.client("elbv2", **self._client_kwargs_for(region))

        @_aws_retry
        def _describe_load_balancers() -> list[dict]:
            return list(client.get_paginator("describe_load_balancers").paginate())

        try:
            results: list[CloudResourceSummary] = []
            for page in _describe_load_balancers():
                for lb in page.get("LoadBalancers", []):
                    results.append(
                        {
                            "id": lb["LoadBalancerArn"],
                            "name": lb.get("LoadBalancerName", lb["LoadBalancerArn"]),
                            "type": lb.get("Type", "unknown"),
                            "region": region,
                            "status": lb.get("State", {}).get("Code", "unknown"),
                            "created_at": lb.get("CreatedTime"),
                        }
                    )
            return results
        except botocore.exceptions.ClientError as exc:
            raise self._wrap_client_error(exc, "AWS_LOAD_BALANCER_INVENTORY_FAILED") from exc

    def list_scaling_groups(self, region: str) -> list[CloudResourceSummary]:
        client = boto3.client("autoscaling", **self._client_kwargs_for(region))

        @_aws_retry
        def _describe_asgs() -> list[dict]:
            return list(client.get_paginator("describe_auto_scaling_groups").paginate())

        try:
            results: list[CloudResourceSummary] = []
            for page in _describe_asgs():
                for asg in page.get("AutoScalingGroups", []):
                    results.append(
                        {
                            "id": asg["AutoScalingGroupARN"],
                            "name": asg["AutoScalingGroupName"],
                            "type": "auto_scaling_group",
                            "region": region,
                            "status": f"{len(asg.get('Instances', []))}/{asg.get('DesiredCapacity', 0)} instances",
                            "created_at": asg.get("CreatedTime"),
                        }
                    )
            return results
        except botocore.exceptions.ClientError as exc:
            raise self._wrap_client_error(exc, "AWS_SCALING_GROUP_INVENTORY_FAILED") from exc

    def list_subnets(self, region: str) -> list[CloudResourceSummary]:
        client = boto3.client("ec2", **self._client_kwargs_for(region))

        @_aws_retry
        def _describe_subnets() -> list[dict]:
            return list(client.get_paginator("describe_subnets").paginate())

        try:
            results: list[CloudResourceSummary] = []
            for page in _describe_subnets():
                for subnet in page.get("Subnets", []):
                    name = next(
                        (t["Value"] for t in subnet.get("Tags", []) if t.get("Key") == "Name"),
                        subnet["SubnetId"],
                    )
                    results.append(
                        {
                            "id": subnet["SubnetId"],
                            "name": name,
                            "type": "subnet",
                            "region": region,
                            "status": subnet.get("State", "unknown"),
                            "created_at": None,
                        }
                    )
            return results
        except botocore.exceptions.ClientError as exc:
            raise self._wrap_client_error(exc, "AWS_SUBNET_INVENTORY_FAILED") from exc

    def list_security_groups(self, region: str) -> list[CloudResourceSummary]:
        client = boto3.client("ec2", **self._client_kwargs_for(region))

        @_aws_retry
        def _describe_security_groups() -> list[dict]:
            return list(client.get_paginator("describe_security_groups").paginate())

        try:
            results: list[CloudResourceSummary] = []
            for page in _describe_security_groups():
                for group in page.get("SecurityGroups", []):
                    results.append(
                        {
                            "id": group["GroupId"],
                            "name": group.get("GroupName", group["GroupId"]),
                            "type": "security_group",
                            "region": region,
                            "status": "active",
                            "created_at": None,
                        }
                    )
            return results
        except botocore.exceptions.ClientError as exc:
            raise self._wrap_client_error(exc, "AWS_SECURITY_GROUP_INVENTORY_FAILED") from exc

    def list_alarms(self, region: str) -> list[CloudResourceSummary]:
        client = boto3.client("cloudwatch", **self._client_kwargs_for(region))

        @_aws_retry
        def _describe_alarms() -> list[dict]:
            return list(client.get_paginator("describe_alarms").paginate())

        try:
            results: list[CloudResourceSummary] = []
            for page in _describe_alarms():
                for alarm in page.get("MetricAlarms", []):
                    results.append(
                        {
                            "id": alarm["AlarmArn"],
                            "name": alarm["AlarmName"],
                            "type": "cloudwatch_alarm",
                            "region": region,
                            "status": alarm.get("StateValue", "unknown"),
                            "created_at": alarm.get("AlarmConfigurationUpdatedTimestamp"),
                        }
                    )
            return results
        except botocore.exceptions.ClientError as exc:
            raise self._wrap_client_error(exc, "AWS_ALARM_INVENTORY_FAILED") from exc

    def list_clusters(self, region: str) -> list[CloudResourceSummary]:
        client = boto3.client("eks", **self._client_kwargs_for(region))

        @_aws_retry
        def _list_cluster_names() -> list[str]:
            return client.list_clusters().get("clusters", [])

        @_aws_retry
        def _describe_cluster(name: str) -> dict:
            return client.describe_cluster(name=name)["cluster"]

        try:
            cluster_names = _list_cluster_names()
            results: list[CloudResourceSummary] = []
            for name in cluster_names:
                detail = _describe_cluster(name)
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

        @_aws_retry
        def _describe_db_instances() -> list[dict]:
            return list(client.get_paginator("describe_db_instances").paginate())

        try:
            results: list[CloudResourceSummary] = []
            for page in _describe_db_instances():
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

        @_aws_retry
        def _list_buckets() -> list[dict]:
            return client.list_buckets().get("Buckets", [])

        try:
            buckets = _list_buckets()
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

        @_aws_retry
        def _describe_vpcs() -> list[dict]:
            return list(client.get_paginator("describe_vpcs").paginate())

        try:
            results: list[CloudResourceSummary] = []
            for page in _describe_vpcs():
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
