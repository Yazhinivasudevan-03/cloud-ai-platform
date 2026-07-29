"""Integration tests for Phase 25D's provisioning endpoints/service -
ownership isolation, confirm-to-destroy, and audit logging - verified
through the real HTTP API against moto's real EC2/S3 emulation (the same
faithful boto3 path test_cloud_sync.py and test_cloud_resource_inventory.py
already rely on). Every test here runs exclusively against moto - none is
capable of touching a real AWS account."""
import json

from moto import mock_aws

from app.models.audit_log import AuditLog
from app.models.cloud_provider_account import CloudProviderAccount
from app.utils.crypto import encrypt_credentials


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_cloud_account(db_session, user_id: int, suffix: str) -> CloudProviderAccount:
    account = CloudProviderAccount(
        user_id=user_id,
        provider="aws",
        account_name=f"provisioning-test-{suffix}",
        region="us-east-1",
        credentials_encrypted=encrypt_credentials({"access_key_id": "testing", "secret_access_key": "testing"}),
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    return account


@mock_aws
def test_deploy_and_destroy_a_real_resource_end_to_end(client, make_user_with_role, db_session):
    token = make_user_with_role("provisioning_op_a", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "a")

    deploy_response = client.post(
        f"/api/v1/cloud-provider-accounts/{account.id}/resources/deploy",
        json={"resource_type": "storage", "region": "us-east-1", "spec": {"name": "my-provisioned-bucket-e2e"}},
        headers=_auth_header(token),
    )
    assert deploy_response.status_code == 201
    resource = deploy_response.json()
    assert resource["id"] == "my-provisioned-bucket-e2e"

    # A successful deploy is recorded in the audit log.
    deploy_logs = (
        db_session.query(AuditLog)
        .filter(AuditLog.user_id == me["id"], AuditLog.action == "cloud_resource_deploy")
        .all()
    )
    assert len(deploy_logs) == 1
    details = json.loads(deploy_logs[0].details)
    assert details["resource_id"] == "my-provisioned-bucket-e2e"
    assert details["outcome"] == "success"

    destroy_response = client.request(
        "DELETE",
        f"/api/v1/cloud-provider-accounts/{account.id}/resources/storage/my-provisioned-bucket-e2e",
        json={"region": "us-east-1", "confirm": "my-provisioned-bucket-e2e"},
        headers=_auth_header(token),
    )
    assert destroy_response.status_code == 204

    destroy_logs = (
        db_session.query(AuditLog)
        .filter(AuditLog.user_id == me["id"], AuditLog.action == "cloud_resource_destroy")
        .all()
    )
    assert len(destroy_logs) == 1
    assert json.loads(destroy_logs[0].details)["outcome"] == "success"


@mock_aws
def test_destroy_rejects_a_confirmation_mismatch(client, make_user_with_role, db_session):
    token = make_user_with_role("provisioning_op_b", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "b")

    client.post(
        f"/api/v1/cloud-provider-accounts/{account.id}/resources/deploy",
        json={"resource_type": "storage", "region": "us-east-1", "spec": {"name": "my-precious-bucket"}},
        headers=_auth_header(token),
    )

    response = client.request(
        "DELETE",
        f"/api/v1/cloud-provider-accounts/{account.id}/resources/storage/my-precious-bucket",
        json={"region": "us-east-1", "confirm": "not-the-right-name"},
        headers=_auth_header(token),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DESTROY_CONFIRMATION_MISMATCH"


def test_deploy_rejects_an_invalid_resource_type(client, make_user_with_role, db_session):
    token = make_user_with_role("provisioning_op_c", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "c")

    response = client.post(
        f"/api/v1/cloud-provider-accounts/{account.id}/resources/deploy",
        json={"resource_type": "clusters", "region": "us-east-1", "spec": {}},
        headers=_auth_header(token),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PROVISIONABLE_RESOURCE_TYPE"


def test_deploy_rejects_a_non_owner(client, make_user_with_role, db_session):
    owner_token = make_user_with_role("provisioning_owner_d", "operator")
    other_token = make_user_with_role("provisioning_other_d", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(owner_token)).json()
    account = _make_cloud_account(db_session, me["id"], "d")

    response = client.post(
        f"/api/v1/cloud-provider-accounts/{account.id}/resources/deploy",
        json={"resource_type": "storage", "region": "us-east-1", "spec": {"name": "someone-elses-bucket"}},
        headers=_auth_header(other_token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_YOUR_CLOUD_ACCOUNT"


def test_destroy_rejects_a_non_owner(client, make_user_with_role, db_session):
    owner_token = make_user_with_role("provisioning_owner_e", "operator")
    other_token = make_user_with_role("provisioning_other_e", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(owner_token)).json()
    account = _make_cloud_account(db_session, me["id"], "e")

    response = client.request(
        "DELETE",
        f"/api/v1/cloud-provider-accounts/{account.id}/resources/storage/some-bucket",
        json={"region": "us-east-1", "confirm": "some-bucket"},
        headers=_auth_header(other_token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_YOUR_CLOUD_ACCOUNT"


@mock_aws
def test_deploy_failure_is_still_recorded_in_the_audit_log(client, make_user_with_role, db_session):
    token = make_user_with_role("provisioning_op_f", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "f")

    # Missing spec.image_id - a real, expected AWS_DEPLOY_SPEC_INCOMPLETE
    # failure, not a fabricated one.
    response = client.post(
        f"/api/v1/cloud-provider-accounts/{account.id}/resources/deploy",
        json={"resource_type": "compute", "region": "us-east-1", "spec": {}},
        headers=_auth_header(token),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AWS_DEPLOY_SPEC_INCOMPLETE"

    logs = (
        db_session.query(AuditLog)
        .filter(AuditLog.user_id == me["id"], AuditLog.action == "cloud_resource_deploy")
        .all()
    )
    assert len(logs) == 1
    assert json.loads(logs[0].details)["outcome"] != "success"
