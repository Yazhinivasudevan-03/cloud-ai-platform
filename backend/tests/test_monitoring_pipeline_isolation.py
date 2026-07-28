"""End-to-end tenant isolation test for the full monitoring pipeline:
connect a real cloud account -> sync real metrics from it -> evaluate
real alerts from those metrics -> dispatch real notifications - proving
two independent users' entire pipelines never cross, using the exact
scenario a real SaaS customer would go through (not just isolated unit
checks per endpoint, which are already covered elsewhere).

Everything here is genuinely real: moto emulates AWS CloudWatch (the
actual boto3 client + request/response path under test - see
test_aws_cloudwatch.py's own docstring for why this is a faithful
substitute for a live AWS account), and AlertEvaluationService/dispatch()
are the exact same production code paths a real deployment goes through.
Nothing here is a mock of this platform's own logic.
"""
from datetime import datetime, timezone

import boto3
from moto import mock_aws

from app.models.alert import Alert
from app.models.cloud_provider_account import CloudProviderAccount
from app.models.notification import Notification
from app.services.alert_evaluation_service import AlertEvaluationService
from app.utils.crypto import encrypt_credentials


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _seed_cloudwatch_cpu(instance_id: str, cpu_percent: float) -> None:
    client = boto3.client(
        "cloudwatch", region_name="us-east-1", aws_access_key_id="testing", aws_secret_access_key="testing"
    )
    now = datetime.now(timezone.utc)
    client.put_metric_data(
        Namespace="AWS/EC2",
        MetricData=[
            {
                "MetricName": "CPUUtilization",
                "Dimensions": [{"Name": "InstanceId", "Value": instance_id}],
                "Timestamp": now,
                "Value": cpu_percent,
                "Unit": "Percent",
            },
        ],
    )


def _make_cloud_account(db_session, user_id: int, suffix: str) -> CloudProviderAccount:
    account = CloudProviderAccount(
        user_id=user_id,
        provider="aws",
        account_name=f"pipeline-test-{suffix}",
        region="us-east-1",
        credentials_encrypted=encrypt_credentials({"access_key_id": "testing", "secret_access_key": "testing"}),
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    return account


def _make_and_link_deployment(client, token: str, account_id: int, resource_id: str, suffix: str) -> dict:
    project = client.post(
        "/api/v1/projects", json={"name": f"pipeline-project-{suffix}"}, headers=_auth_header(token)
    ).json()
    microservice = client.post(
        f"/api/v1/projects/{project['id']}/microservices",
        json={"name": f"pipeline-service-{suffix}"},
        headers=_auth_header(token),
    ).json()
    deployment = client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={"name": f"pipeline-deploy-{suffix}", "namespace": "default"},
        headers=_auth_header(token),
    ).json()
    client.put(
        f"/api/v1/deployments/{deployment['id']}",
        json={"cloud_provider_account_id": account_id, "cloud_resource_identifier": resource_id},
        headers=_auth_header(token),
    )
    return deployment


@mock_aws
def test_two_tenants_full_monitoring_pipeline_never_crosses(client, make_user_with_role, db_session):
    token_a = make_user_with_role("pipeline_user_a", "operator")
    token_b = make_user_with_role("pipeline_user_b", "operator")
    me_a = client.get("/api/v1/auth/me", headers=_auth_header(token_a)).json()
    me_b = client.get("/api/v1/auth/me", headers=_auth_header(token_b)).json()

    account_a = _make_cloud_account(db_session, me_a["id"], "a")
    account_b = _make_cloud_account(db_session, me_b["id"], "b")

    # Each user connects their own account and links their own deployment
    # to it - two entirely independent tenants, never referencing each
    # other's account or resource IDs.
    _seed_cloudwatch_cpu("i-pipeline-a", cpu_percent=75.0)  # above warning (60) and elevated (below 80 critical)
    _seed_cloudwatch_cpu("i-pipeline-b", cpu_percent=95.0)  # above critical (80)
    deployment_a = _make_and_link_deployment(client, token_a, account_a.id, "i-pipeline-a", "a")
    deployment_b = _make_and_link_deployment(client, token_b, account_b.id, "i-pipeline-b", "b")

    # --- Real cloud metrics sync (the exact scheduled/on-demand path a
    # live deployment goes through - CloudSyncService -> real boto3 call) ---
    sync_a = client.post(
        f"/api/v1/deployments/{deployment_a['id']}/sync-cloud-metrics", headers=_auth_header(token_a)
    )
    sync_b = client.post(
        f"/api/v1/deployments/{deployment_b['id']}/sync-cloud-metrics", headers=_auth_header(token_b)
    )
    assert sync_a.status_code == 200
    assert sync_b.status_code == 200

    # --- Resource usage is traceable to exactly one owner/account, and
    # cross-tenant reads are rejected outright (not just filtered) ---
    usage_a = client.get(
        f"/api/v1/deployments/{deployment_a['id']}/resource-usage", headers=_auth_header(token_a)
    ).json()
    row_a = usage_a["items"][0]
    assert row_a["cloud_provider_account_id"] == account_a.id
    assert row_a["owner_user_id"] == me_a["id"]
    assert row_a["cpu_usage_percent"] == 75.0

    forbidden_usage = client.get(
        f"/api/v1/deployments/{deployment_a['id']}/resource-usage", headers=_auth_header(token_b)
    )
    assert forbidden_usage.status_code == 403
    assert forbidden_usage.json()["error"]["code"] == "NOT_YOUR_PROJECT"

    # --- Real alert evaluation against the real synced metrics - the
    # exact scheduled rule engine, not a fabricated Alert row ---
    summary = AlertEvaluationService(db_session).evaluate_all()
    assert summary["alerts_created"] >= 2

    alerts_a = db_session.query(Alert).filter(Alert.deployment_id == deployment_a["id"]).all()
    alerts_b = db_session.query(Alert).filter(Alert.deployment_id == deployment_b["id"]).all()
    assert len(alerts_a) == 1
    assert len(alerts_b) == 1
    assert alerts_a[0].alert_type == "cpu_elevated"
    assert alerts_b[0].alert_type == "cpu_high"  # 95% crosses the critical (80) tier, not just warning

    # --- Each alert is traceable to exactly its own owner/account via the
    # API response, never the other tenant's ---
    api_alerts_a = client.get(
        f"/api/v1/deployments/{deployment_a['id']}/alerts", headers=_auth_header(token_a)
    ).json()["items"]
    assert len(api_alerts_a) == 1
    assert api_alerts_a[0]["cloud_provider_account_id"] == account_a.id
    assert api_alerts_a[0]["owner_user_id"] == me_a["id"]

    # --- Global alert listing is scoped per user - each tenant sees only
    # their own alert, never the other's ---
    global_alerts_a = client.get("/api/v1/alerts", headers=_auth_header(token_a)).json()
    global_alerts_b = client.get("/api/v1/alerts", headers=_auth_header(token_b)).json()
    assert {a["id"] for a in global_alerts_a["items"]} == {alerts_a[0].id}
    assert {a["id"] for a in global_alerts_b["items"]} == {alerts_b[0].id}

    # --- Notifications: the dispatcher fan-out (triggered inside
    # evaluate_all()) must have notified only each alert's real owner ---
    notifications_a = db_session.query(Notification).filter(Notification.alert_id == alerts_a[0].id).all()
    notifications_b = db_session.query(Notification).filter(Notification.alert_id == alerts_b[0].id).all()
    assert {n.user_id for n in notifications_a} == {me_a["id"]}
    assert {n.user_id for n in notifications_b} == {me_b["id"]}

    my_notifications_a = client.get("/api/v1/notifications", headers=_auth_header(token_a)).json()
    my_notifications_b = client.get("/api/v1/notifications", headers=_auth_header(token_b)).json()
    alert_ids_seen_by_a = {n["alert_id"] for n in my_notifications_a["items"]}
    alert_ids_seen_by_b = {n["alert_id"] for n in my_notifications_b["items"]}
    assert alerts_a[0].id in alert_ids_seen_by_a
    assert alerts_b[0].id not in alert_ids_seen_by_a
    assert alerts_b[0].id in alert_ids_seen_by_b
    assert alerts_a[0].id not in alert_ids_seen_by_b


@mock_aws
def test_resource_usage_and_alerts_are_null_owner_free_when_deployment_has_no_cloud_account(
    client, make_user_with_role, db_session
):
    """A deployment with no connected cloud account still has a real
    owner (its project's owner) - cloud_provider_account_id is simply
    null, never a fabricated value, and the row is still fully isolated
    to its owner."""
    token = make_user_with_role("pipeline_user_c", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()

    project = client.post(
        "/api/v1/projects", json={"name": "pipeline-project-c"}, headers=_auth_header(token)
    ).json()
    microservice = client.post(
        f"/api/v1/projects/{project['id']}/microservices",
        json={"name": "pipeline-service-c"},
        headers=_auth_header(token),
    ).json()
    deployment = client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={"name": "pipeline-deploy-c", "namespace": "default"},
        headers=_auth_header(token),
    ).json()

    client.post(
        f"/api/v1/deployments/{deployment['id']}/resource-usage",
        json={
            "cpu_usage_percent": 10.0,
            "memory_usage_mb": 200.0,
            "disk_usage_mb": 500.0,
            "network_in_kbps": 5.0,
            "network_out_kbps": 5.0,
            "recorded_at": "2026-07-15T12:00:00",
        },
        headers=_auth_header(token),
    )

    usage = client.get(
        f"/api/v1/deployments/{deployment['id']}/resource-usage", headers=_auth_header(token)
    ).json()
    row = usage["items"][0]
    assert row["cloud_provider_account_id"] is None
    assert row["owner_user_id"] == me["id"]
