"""Integration tests for real-time cloud metrics syncing (Phase 12) -
verified against moto's CloudWatch emulation, exercising the full real
path: deployment -> linked cloud account -> real boto3 CloudWatch call
-> resource_usage row, through the actual HTTP API."""
from datetime import datetime, timezone

import boto3
import pytest
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


@mock_aws
@pytest.mark.parametrize(
    "cpu_usage_percent,expected_alert_type,expected_severity",
    [
        (60.0, "cpu_elevated", "warning"),
        (80.0, "cpu_high", "critical"),
        (100.0, "cpu_saturated", "critical"),
    ],
)
def test_cloud_synced_cpu_usage_triggers_correct_alert_and_notification(
    client, make_user_with_role, db_session, cpu_usage_percent, expected_alert_type, expected_severity
):
    """Proves the full real chain end to end for genuinely cloud-sourced
    data (not manually-POSTed usage): a real boto3 CloudWatch call (via
    moto) -> CloudSyncService writes a resource_usage row -> the existing,
    source-agnostic AlertEvaluationService reads that same row and fires
    the correct alert tier and a dashboard notification - at each of the
    three configured CPU thresholds (60/80/100)."""
    from app.services.alert_evaluation_service import AlertEvaluationService

    admin_token = make_user_with_role(f"cloud_alert_admin_{int(cpu_usage_percent)}", "admin")
    me = client.get("/api/v1/auth/me", headers=_auth_header(admin_token)).json()
    account = _make_cloud_account(db_session, me["id"])
    deployment = _make_deployment(client, admin_token, f"alert-{int(cpu_usage_percent)}")

    resource_id = f"i-alert-test-{int(cpu_usage_percent)}"
    client.put(
        f"/api/v1/deployments/{deployment['id']}",
        json={"cloud_provider_account_id": account.id, "cloud_resource_identifier": resource_id},
        headers=_auth_header(admin_token),
    )

    client_boto = boto3.client(
        "cloudwatch", region_name="us-east-1", aws_access_key_id="testing", aws_secret_access_key="testing"
    )
    now = datetime.now(timezone.utc)
    client_boto.put_metric_data(
        Namespace="AWS/EC2",
        MetricData=[
            {
                "MetricName": "CPUUtilization",
                "Dimensions": [{"Name": "InstanceId", "Value": resource_id}],
                "Timestamp": now,
                "Value": cpu_usage_percent,
                "Unit": "Percent",
            },
        ],
    )

    sync_resp = client.post(
        f"/api/v1/deployments/{deployment['id']}/sync-cloud-metrics", headers=_auth_header(admin_token)
    )
    assert sync_resp.status_code == 200

    AlertEvaluationService(db_session).evaluate_all()

    from app.models.alert import Alert

    alert = (
        db_session.query(Alert)
        .filter(Alert.deployment_id == deployment["id"], Alert.status == "active")
        .one()
    )
    assert alert.alert_type == expected_alert_type
    assert alert.severity == expected_severity

    notifications_resp = client.get(
        "/api/v1/notifications", headers=_auth_header(admin_token)
    )
    assert notifications_resp.status_code == 200
    assert notifications_resp.json()["meta"]["total"] >= 1


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
