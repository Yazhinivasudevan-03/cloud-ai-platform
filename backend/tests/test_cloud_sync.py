"""Integration tests for real-time cloud metrics syncing (Phase 12) -
verified against moto's CloudWatch emulation, exercising the full real
path: deployment -> linked cloud account -> real boto3 CloudWatch call
-> resource_usage row, through the actual HTTP API."""
from datetime import datetime, timezone

import boto3
from moto import mock_aws

from app.models.cloud_provider_account import CloudProviderAccount
from app.utils.crypto import encrypt_credentials


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _seed_cloudwatch_datapoint(instance_id: str) -> None:
    client = boto3.client(
        "cloudwatch",
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    now = datetime.now(timezone.utc)
    client.put_metric_data(
        Namespace="AWS/EC2",
        MetricData=[
            {
                "MetricName": "CPUUtilization",
                "Dimensions": [{"Name": "InstanceId", "Value": instance_id}],
                "Timestamp": now,
                "Value": 55.0,
                "Unit": "Percent",
            },
            {
                "MetricName": "NetworkIn",
                "Dimensions": [{"Name": "InstanceId", "Value": instance_id}],
                "Timestamp": now,
                "Value": 2_000_000.0,
                "Unit": "Bytes",
            },
            {
                "MetricName": "NetworkOut",
                "Dimensions": [{"Name": "InstanceId", "Value": instance_id}],
                "Timestamp": now,
                "Value": 1_000_000.0,
                "Unit": "Bytes",
            },
        ],
    )


def _make_cloud_account(db_session, user_id: int, provider: str = "aws") -> CloudProviderAccount:
    account = CloudProviderAccount(
        user_id=user_id,
        provider=provider,
        account_name=f"test-{provider}-{user_id}",
        region="us-east-1",
        credentials_encrypted=encrypt_credentials(
            {"access_key_id": "testing", "secret_access_key": "testing"}
        ),
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    return account


def _make_deployment(client, token, suffix: str) -> dict:
    project = client.post(
        "/api/v1/projects", json={"name": f"cs-project-{suffix}"}, headers=_auth_header(token)
    ).json()
    microservice = client.post(
        f"/api/v1/projects/{project['id']}/microservices",
        json={"name": f"cs-service-{suffix}"},
        headers=_auth_header(token),
    ).json()
    return client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={"name": f"cs-deploy-{suffix}", "namespace": "default"},
        headers=_auth_header(token),
    ).json()


@mock_aws
def test_sync_cloud_metrics_writes_real_resource_usage(client, make_user_with_role, db_session):
    token = make_user_with_role("cloud_sync_op_a", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"])
    deployment = _make_deployment(client, token, "a")

    link_resp = client.put(
        f"/api/v1/deployments/{deployment['id']}",
        json={"cloud_provider_account_id": account.id, "cloud_resource_identifier": "i-real-test-a"},
        headers=_auth_header(token),
    )
    assert link_resp.status_code == 200
    assert link_resp.json()["cloud_resource_identifier"] == "i-real-test-a"

    _seed_cloudwatch_datapoint("i-real-test-a")

    sync_resp = client.post(
        f"/api/v1/deployments/{deployment['id']}/sync-cloud-metrics", headers=_auth_header(token)
    )
    assert sync_resp.status_code == 200
    body = sync_resp.json()
    assert body["provider"] == "aws"
    assert body["resource_identifier"] == "i-real-test-a"
    assert body["cloud_provider_account_id"] == account.id

    usage_resp = client.get(
        f"/api/v1/deployments/{deployment['id']}/resource-usage", headers=_auth_header(token)
    )
    assert usage_resp.status_code == 200
    items = usage_resp.json()["items"]
    assert len(items) == 1
    assert items[0]["cpu_usage_percent"] == 55.0


def test_sync_fails_clearly_when_deployment_has_no_cloud_link(client, make_user_with_role):
    token = make_user_with_role("cloud_sync_op_b", "operator")
    deployment = _make_deployment(client, token, "b")

    response = client.post(
        f"/api/v1/deployments/{deployment['id']}/sync-cloud-metrics", headers=_auth_header(token)
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CLOUD_SYNC_NOT_CONFIGURED"


def test_sync_fails_clearly_for_unsupported_provider(client, make_user_with_role, db_session):
    token = make_user_with_role("cloud_sync_op_c", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], provider="azure")
    deployment = _make_deployment(client, token, "c")

    client.put(
        f"/api/v1/deployments/{deployment['id']}",
        json={"cloud_provider_account_id": account.id, "cloud_resource_identifier": "vm-test"},
        headers=_auth_header(token),
    )

    response = client.post(
        f"/api/v1/deployments/{deployment['id']}/sync-cloud-metrics", headers=_auth_header(token)
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CLOUD_SYNC_PROVIDER_NOT_SUPPORTED"


@mock_aws
def test_sync_all_tolerates_individual_failures(client, make_user_with_role, db_session):
    """The scheduled job (CloudSyncService.sync_all) must not abort the
    whole run just because one deployment's sync fails - e.g. a different
    deployment linked to an unsupported provider shouldn't block a working
    AWS-linked deployment from being synced in the same pass."""
    from app.services.cloud_sync_service import CloudSyncService

    token = make_user_with_role("cloud_sync_op_f", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()

    working_account = _make_cloud_account(db_session, me["id"], provider="aws")
    working_deployment = _make_deployment(client, token, "f-working")
    client.put(
        f"/api/v1/deployments/{working_deployment['id']}",
        json={
            "cloud_provider_account_id": working_account.id,
            "cloud_resource_identifier": "i-real-test-f",
        },
        headers=_auth_header(token),
    )
    _seed_cloudwatch_datapoint("i-real-test-f")

    broken_account = _make_cloud_account(db_session, me["id"], provider="gcp")
    broken_deployment = _make_deployment(client, token, "f-broken")
    client.put(
        f"/api/v1/deployments/{broken_deployment['id']}",
        json={"cloud_provider_account_id": broken_account.id, "cloud_resource_identifier": "vm-test"},
        headers=_auth_header(token),
    )

    summary = CloudSyncService(db_session).sync_all()

    assert summary.deployments_attempted == 2
    assert summary.deployments_synced == 1
    assert summary.deployments_failed == 1


def test_cannot_link_deployment_to_another_users_cloud_account(
    client, make_user_with_role, db_session
):
    token_a = make_user_with_role("cloud_sync_op_d", "operator")
    token_b = make_user_with_role("cloud_sync_op_e", "operator")
    me_b = client.get("/api/v1/auth/me", headers=_auth_header(token_b)).json()
    account_b = _make_cloud_account(db_session, me_b["id"])

    deployment = _make_deployment(client, token_a, "d")

    response = client.put(
        f"/api/v1/deployments/{deployment['id']}",
        json={"cloud_provider_account_id": account_b.id, "cloud_resource_identifier": "i-not-yours"},
        headers=_auth_header(token_a),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_YOUR_CLOUD_ACCOUNT"
