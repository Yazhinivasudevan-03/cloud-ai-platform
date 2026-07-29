"""Integration tests for Phase 25C's resource inventory endpoint/service -
category dispatch, single-region vs. "all regions" aggregation, and
ownership isolation - verified through the real HTTP API against moto's
real EC2 emulation (the same faithful boto3 path test_cloud_sync.py and
test_cloud_region_sync.py already rely on)."""
import json

import boto3
from moto import mock_aws

from app.models.cloud_provider_account import CloudProviderAccount
from app.utils.crypto import encrypt_credentials


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_cloud_account(db_session, user_id: int, suffix: str, available_regions: list[str] | None = None):
    account = CloudProviderAccount(
        user_id=user_id,
        provider="aws",
        account_name=f"inventory-test-{suffix}",
        region="us-east-1",
        credentials_encrypted=encrypt_credentials({"access_key_id": "testing", "secret_access_key": "testing"}),
        available_regions=json.dumps(
            [{"id": r, "display_name": r} for r in (available_regions or [])]
        ),
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    return account


@mock_aws
def test_list_resources_for_a_single_region(client, make_user_with_role, db_session):
    token = make_user_with_role("inventory_op_a", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "a")

    ec2 = boto3.client("ec2", region_name="us-east-1")
    ec2.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1, InstanceType="t2.micro")

    response = client.get(
        f"/api/v1/cloud-provider-accounts/{account.id}/resources?category=compute&region=us-east-1",
        headers=_auth_header(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "compute"
    assert body["region"] == "us-east-1"
    assert len(body["items"]) == 1
    assert body["items"][0]["type"] == "t2.micro"


@mock_aws
def test_list_resources_aggregates_across_all_discovered_regions(client, make_user_with_role, db_session):
    token = make_user_with_role("inventory_op_b", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "b", available_regions=["us-east-1", "us-west-2"])

    boto3.client("ec2", region_name="us-east-1").run_instances(
        ImageId="ami-1", MinCount=1, MaxCount=1, InstanceType="t2.micro"
    )
    boto3.client("ec2", region_name="us-west-2").run_instances(
        ImageId="ami-2", MinCount=1, MaxCount=1, InstanceType="t3.micro"
    )

    response = client.get(
        f"/api/v1/cloud-provider-accounts/{account.id}/resources?category=compute&region=all",
        headers=_auth_header(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    regions_seen = {item["region"] for item in body["items"]}
    assert regions_seen == {"us-east-1", "us-west-2"}


def test_list_resources_rejects_all_regions_when_none_discovered_yet(client, make_user_with_role, db_session):
    token = make_user_with_role("inventory_op_c", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "c")

    response = client.get(
        f"/api/v1/cloud-provider-accounts/{account.id}/resources?category=compute&region=all",
        headers=_auth_header(token),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NO_REGIONS_DISCOVERED"


def test_list_resources_rejects_an_invalid_category(client, make_user_with_role, db_session):
    token = make_user_with_role("inventory_op_d", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "d")

    response = client.get(
        f"/api/v1/cloud-provider-accounts/{account.id}/resources?category=not-a-real-category&region=us-east-1",
        headers=_auth_header(token),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_RESOURCE_CATEGORY"


def test_list_resources_rejects_a_non_owner(client, make_user_with_role, db_session):
    owner_token = make_user_with_role("inventory_owner_e", "operator")
    other_token = make_user_with_role("inventory_other_e", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(owner_token)).json()
    account = _make_cloud_account(db_session, me["id"], "e")

    response = client.get(
        f"/api/v1/cloud-provider-accounts/{account.id}/resources?category=compute&region=us-east-1",
        headers=_auth_header(other_token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_YOUR_CLOUD_ACCOUNT"
