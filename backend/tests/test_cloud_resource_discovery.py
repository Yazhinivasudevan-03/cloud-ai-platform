"""Unit/integration tests for Phase 29's automatic AWS resource discovery -
CloudResourceDiscoveryService's upsert/diff/appear-disappear logic, the
per-account failure tolerance in discover_all(), and its CloudWatch
metrics collection gated on a running EC2 instance's status. Verified
against moto's real EC2/S3/CloudWatch emulation, the same faithful boto3
request path this project already relies on elsewhere - EC2 instance
inventory is patched at the provider-client boundary in a few tests to
deterministically control instance status (running vs stopped) rather
than depending on moto's own EC2 lifecycle timing."""
from datetime import datetime, timezone
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from app.models.cloud_provider_account import CloudProviderAccount
from app.repositories.cloud_resource_repository import CloudResourceRepository
from app.services.cloud_resource_discovery_service import CloudResourceDiscoveryService
from app.utils.crypto import encrypt_credentials
from app.utils.exceptions import ValidationAppError

_PATCH_TARGET = "app.integrations.providers.aws_provider.AwsCloudProviderClient.list_ec2_instances_detailed"


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_cloud_account(db_session, user_id: int, suffix: str) -> CloudProviderAccount:
    account = CloudProviderAccount(
        user_id=user_id,
        provider="aws",
        account_name=f"discovery-test-{suffix}",
        region="us-east-1",
        credentials_encrypted=encrypt_credentials({"access_key_id": "testing", "secret_access_key": "testing"}),
        credentials_validated=True,
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    return account


def _fake_instance(instance_id: str, status: str, name: str = "box") -> dict:
    return {
        "id": instance_id,
        "name": name,
        "instance_type": "t2.micro",
        "region": "us-east-1",
        "availability_zone": "us-east-1a",
        "status": status,
        "public_ip": None,
        "private_ip": "10.0.0.5",
        "tags": {"Name": name},
        "created_at": None,
    }


@mock_aws
def test_discover_account_persists_real_ec2_and_s3_resources(client, make_user_with_role, db_session):
    token = make_user_with_role("discovery_op_a", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "a")

    ec2 = boto3.client("ec2", region_name="us-east-1", aws_access_key_id="testing", aws_secret_access_key="testing")
    ec2.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1, InstanceType="t2.micro")
    s3 = boto3.client("s3", region_name="us-east-1", aws_access_key_id="testing", aws_secret_access_key="testing")
    s3.create_bucket(Bucket="discovery-test-bucket")

    CloudResourceDiscoveryService(db_session).discover_account(account.id, me["id"])

    repo = CloudResourceRepository(db_session)
    ec2_resources = repo.list_for_account(account.id, resource_type="ec2_instance")
    s3_resources = repo.list_for_account(account.id, resource_type="s3_bucket")

    assert len(ec2_resources) == 1
    assert ec2_resources[0].user_id == me["id"]
    assert ec2_resources[0].instance_type == "t2.micro"
    assert ec2_resources[0].region == "us-east-1"
    assert len(s3_resources) == 1
    assert s3_resources[0].external_id == "discovery-test-bucket"

    db_session.refresh(account)
    assert account.last_discovery_at is not None
    assert account.last_discovery_error is None


@mock_aws
def test_discover_account_collects_cloudwatch_metrics_only_for_running_instances(
    client, make_user_with_role, db_session
):
    token = make_user_with_role("discovery_op_metrics", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "metrics")

    cloudwatch = boto3.client(
        "cloudwatch", region_name="us-east-1", aws_access_key_id="testing", aws_secret_access_key="testing"
    )
    now = datetime.now(timezone.utc)
    for instance_id in ("i-running-1", "i-stopped-1"):
        cloudwatch.put_metric_data(
            Namespace="AWS/EC2",
            MetricData=[
                {
                    "MetricName": "CPUUtilization",
                    "Dimensions": [{"Name": "InstanceId", "Value": instance_id}],
                    "Timestamp": now,
                    "Value": 42.0,
                    "Unit": "Percent",
                }
            ],
        )

    fake_instances = [
        _fake_instance("i-running-1", "running", "running-box"),
        _fake_instance("i-stopped-1", "stopped", "stopped-box"),
    ]

    with patch(_PATCH_TARGET, return_value=fake_instances):
        CloudResourceDiscoveryService(db_session).discover_account(account.id, me["id"])

    repo = CloudResourceRepository(db_session)
    resources = repo.list_for_account(account.id, resource_type="ec2_instance")
    by_external_id = {r.external_id: r for r in resources}
    assert len(resources) == 2

    running_metric = repo.get_latest_metric(by_external_id["i-running-1"].id)
    stopped_metric = repo.get_latest_metric(by_external_id["i-stopped-1"].id)
    assert running_metric is not None
    assert running_metric.cpu_usage_percent == pytest.approx(42.0)
    assert stopped_metric is None


@mock_aws
def test_discover_account_marks_disappeared_instances_inactive_and_reactivates_them(
    client, make_user_with_role, db_session
):
    token = make_user_with_role("discovery_op_disappear", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "disappear")

    present = [_fake_instance("i-temp-1", "running", "temp-box")]

    with patch(_PATCH_TARGET, return_value=present):
        CloudResourceDiscoveryService(db_session).discover_account(account.id, me["id"])
    resource = CloudResourceRepository(db_session).list_for_account(
        account.id, resource_type="ec2_instance", active_only=False
    )[0]
    assert resource.is_active is True

    # A subsequent pass that no longer observes the instance (terminated in
    # the real account) must flip it inactive without deleting the row.
    with patch(_PATCH_TARGET, return_value=[]):
        CloudResourceDiscoveryService(db_session).discover_account(account.id, me["id"])
    db_session.refresh(resource)
    assert resource.is_active is False

    # And it auto-reappears (is_active flips back True) if seen again,
    # with no reconnect action required.
    with patch(_PATCH_TARGET, return_value=present):
        CloudResourceDiscoveryService(db_session).discover_account(account.id, me["id"])
    db_session.refresh(resource)
    assert resource.is_active is True


@mock_aws
def test_discover_account_raises_and_records_the_real_error_on_genuine_failure(
    client, make_user_with_role, db_session
):
    token = make_user_with_role("discovery_op_fail", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "fail")

    with patch(_PATCH_TARGET, side_effect=ValidationAppError("boom", code="AWS_RESOURCE_INVENTORY_FAILED")):
        with pytest.raises(ValidationAppError) as exc_info:
            CloudResourceDiscoveryService(db_session).discover_account(account.id, me["id"])

    assert exc_info.value.code == "CLOUD_RESOURCE_DISCOVERY_FAILED"
    assert "boom" in str(exc_info.value)

    db_session.refresh(account)
    assert account.last_discovery_error is not None
    assert "boom" in account.last_discovery_error


@mock_aws
def test_discover_account_aggregates_across_every_region_in_all_mode(client, make_user_with_role, db_session):
    # Requirement 7 (Phase 30): "All Regions" mode must discover/persist
    # resources from every one of the account's discovered regions, not
    # just its (irrelevant, in "all" mode) selected_region column.
    token = make_user_with_role("discovery_op_all_regions", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = CloudProviderAccount(
        user_id=me["id"],
        provider="aws",
        account_name="discovery-test-all-regions",
        region="all",
        credentials_encrypted=encrypt_credentials({"access_key_id": "testing", "secret_access_key": "testing"}),
        credentials_validated=True,
        available_regions=(
            '[{"id": "us-east-1", "display_name": "N. Virginia", "country": "United States", '
            '"timezone": "America/New_York"}, {"id": "us-west-2", "display_name": "Oregon", '
            '"country": "United States", "timezone": "America/Los_Angeles"}]'
        ),
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    for region in ("us-east-1", "us-west-2"):
        ec2 = boto3.client(
            "ec2", region_name=region, aws_access_key_id="testing", aws_secret_access_key="testing"
        )
        ec2.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1, InstanceType="t2.micro")

    CloudResourceDiscoveryService(db_session).discover_account(account.id, me["id"])

    resources = CloudResourceRepository(db_session).list_for_account(account.id, resource_type="ec2_instance")
    regions_seen = {r.region for r in resources}
    assert regions_seen == {"us-east-1", "us-west-2"}


def test_discover_account_raises_a_clear_error_when_all_mode_has_no_discovered_regions(
    client, make_user_with_role, db_session
):
    token = make_user_with_role("discovery_op_all_no_regions", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = CloudProviderAccount(
        user_id=me["id"],
        provider="aws",
        account_name="discovery-test-all-no-regions",
        region="all",
        credentials_encrypted=encrypt_credentials({"access_key_id": "testing", "secret_access_key": "testing"}),
        credentials_validated=True,
    )
    db_session.add(account)
    db_session.commit()

    with pytest.raises(ValidationAppError) as exc_info:
        CloudResourceDiscoveryService(db_session).discover_account(account.id, me["id"])
    assert exc_info.value.code == "NO_REGIONS_DISCOVERED"


def test_discover_all_tolerates_a_failing_account(client, make_user_with_role, db_session):
    token_a = make_user_with_role("discovery_op_all_a", "operator")
    token_b = make_user_with_role("discovery_op_all_b", "operator")
    me_a = client.get("/api/v1/auth/me", headers=_auth_header(token_a)).json()
    me_b = client.get("/api/v1/auth/me", headers=_auth_header(token_b)).json()

    good_account = _make_cloud_account(db_session, me_a["id"], "good")
    bad_account = CloudProviderAccount(
        user_id=me_b["id"],
        provider="not_a_real_provider",
        account_name="discovery-test-broken",
        region="nowhere-1",
        credentials_encrypted=encrypt_credentials({"anything": "goes"}),
        credentials_validated=True,
    )
    db_session.add(bad_account)
    db_session.commit()

    with mock_aws():
        summary = CloudResourceDiscoveryService(db_session).discover_all()

    assert summary.accounts_attempted == 2
    assert summary.accounts_discovered == 1
    assert summary.accounts_failed == 1


def test_discover_all_skips_an_account_with_unvalidated_credentials(client, make_user_with_role, db_session):
    token = make_user_with_role("discovery_op_unvalidated", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    unvalidated_account = CloudProviderAccount(
        user_id=me["id"],
        provider="aws",
        account_name="discovery-test-unvalidated",
        region="us-east-1",
        credentials_encrypted=encrypt_credentials({"access_key_id": "testing", "secret_access_key": "testing"}),
    )
    db_session.add(unvalidated_account)
    db_session.commit()

    summary = CloudResourceDiscoveryService(db_session).discover_all()

    assert summary.accounts_attempted == 0


def test_discover_account_rejects_a_non_owner(client, make_user_with_role, db_session):
    owner_token = make_user_with_role("discovery_owner", "operator")
    other_token = make_user_with_role("discovery_other", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(owner_token)).json()
    other = client.get("/api/v1/auth/me", headers=_auth_header(other_token)).json()
    account = _make_cloud_account(db_session, me["id"], "owner")

    with pytest.raises(Exception) as exc_info:
        CloudResourceDiscoveryService(db_session).discover_account(account.id, other["id"])
    assert getattr(exc_info.value, "code", None) == "NOT_YOUR_CLOUD_ACCOUNT"


def test_discover_account_raises_not_found_for_a_missing_account(client, make_user_with_role, db_session):
    token = make_user_with_role("discovery_missing", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()

    with pytest.raises(Exception) as exc_info:
        CloudResourceDiscoveryService(db_session).discover_account(999999, me["id"])
    assert getattr(exc_info.value, "code", None) == "CLOUD_ACCOUNT_NOT_FOUND"
