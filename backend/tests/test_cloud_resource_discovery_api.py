"""Integration tests for Phase 29's automatic-discovery HTTP endpoints:
GET .../discovered-resources, GET .../discovered-resources/summary, and
POST .../discover-resources - verified against moto's real EC2/S3
emulation."""
import boto3
from moto import mock_aws

from app.models.cloud_provider_account import CloudProviderAccount
from app.utils.crypto import encrypt_credentials

AWS_CREDENTIALS = {"access_key_id": "testing", "secret_access_key": "testing"}


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_cloud_account(db_session, user_id: int, suffix: str) -> CloudProviderAccount:
    account = CloudProviderAccount(
        user_id=user_id,
        provider="aws",
        account_name=f"discovery-api-test-{suffix}",
        region="us-east-1",
        credentials_encrypted=encrypt_credentials(AWS_CREDENTIALS),
        credentials_validated=True,
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    return account


@mock_aws
def test_discover_resources_endpoint_persists_and_returns_a_summary(client, make_user_with_role, db_session):
    token = make_user_with_role("discovery_api_op_a", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "a")

    ec2 = boto3.client("ec2", region_name="us-east-1", aws_access_key_id="testing", aws_secret_access_key="testing")
    ec2.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1, InstanceType="t2.micro")

    response = client.post(
        f"/api/v1/cloud-provider-accounts/{account.id}/discover-resources", headers=_auth_header(token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_instances"] == 1
    assert body["last_discovery_at"] is not None
    assert body["last_discovery_error"] is None


@mock_aws
def test_list_discovered_resources_returns_persisted_ec2_fields(client, make_user_with_role, db_session):
    token = make_user_with_role("discovery_api_op_b", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "b")

    ec2 = boto3.client("ec2", region_name="us-east-1", aws_access_key_id="testing", aws_secret_access_key="testing")
    ec2.run_instances(
        ImageId="ami-12345678",
        MinCount=1,
        MaxCount=1,
        InstanceType="t2.micro",
        TagSpecifications=[{"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": "api-test-box"}]}],
    )
    client.post(f"/api/v1/cloud-provider-accounts/{account.id}/discover-resources", headers=_auth_header(token))

    response = client.get(
        f"/api/v1/cloud-provider-accounts/{account.id}/discovered-resources",
        params={"resource_type": "ec2_instance"},
        headers=_auth_header(token),
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "api-test-box"
    assert items[0]["instance_type"] == "t2.micro"
    assert items[0]["region"] == "us-east-1"
    assert items[0]["is_active"] is True


@mock_aws
def test_discovered_resources_summary_reports_running_and_stopped_counts(client, make_user_with_role, db_session):
    token = make_user_with_role("discovery_api_op_c", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "c")

    s3 = boto3.client("s3", region_name="us-east-1", aws_access_key_id="testing", aws_secret_access_key="testing")
    s3.create_bucket(Bucket="discovery-api-test-bucket")
    client.post(f"/api/v1/cloud-provider-accounts/{account.id}/discover-resources", headers=_auth_header(token))

    response = client.get(
        f"/api/v1/cloud-provider-accounts/{account.id}/discovered-resources/summary", headers=_auth_header(token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["resource_counts_by_type"]["s3_bucket"] == 1
    assert body["last_discovery_at"] is not None


def test_discovery_endpoints_reject_a_non_owner(client, make_user_with_role, db_session):
    owner_token = make_user_with_role("discovery_api_owner", "operator")
    other_token = make_user_with_role("discovery_api_other", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(owner_token)).json()
    account = _make_cloud_account(db_session, me["id"], "owner")

    for method, path in (
        ("get", f"/api/v1/cloud-provider-accounts/{account.id}/discovered-resources"),
        ("get", f"/api/v1/cloud-provider-accounts/{account.id}/discovered-resources/summary"),
        ("post", f"/api/v1/cloud-provider-accounts/{account.id}/discover-resources"),
    ):
        response = getattr(client, method)(path, headers=_auth_header(other_token))
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "NOT_YOUR_CLOUD_ACCOUNT"


def test_discover_resources_endpoint_reports_the_exact_failure_reason(client, make_user_with_role, db_session):
    token = make_user_with_role("discovery_api_op_fail", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    broken_account = CloudProviderAccount(
        user_id=me["id"],
        provider="not_a_real_provider",
        account_name="discovery-api-test-broken",
        region="nowhere-1",
        credentials_encrypted=encrypt_credentials({"anything": "goes"}),
        credentials_validated=True,
    )
    db_session.add(broken_account)
    db_session.commit()

    response = client.post(
        f"/api/v1/cloud-provider-accounts/{broken_account.id}/discover-resources", headers=_auth_header(token)
    )

    # The real reason (an unsupported provider), never a silent empty result.
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CLOUD_PROVIDER_NOT_SUPPORTED"
