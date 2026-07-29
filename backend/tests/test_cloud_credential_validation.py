"""Unit + integration tests for Phase 26's Cloud Credential Configuration
workflow - CloudProviderClient.test_connection(), the stateless
POST /cloud-provider-accounts/test-connection endpoint, and
POST /{account_id}/validate-credentials (which flips credentials_validated
and gates scheduled monitoring sweeps). AWS is verified against moto's real
STS/EC2/IAM emulation; Azure/GCP/OCI/Alibaba patch their SDK clients
directly, mirroring this project's established pattern for providers with
no available emulator."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import boto3
import botocore.exceptions
import pytest
from azure.core.exceptions import ClientAuthenticationError
from moto import mock_aws

from app.integrations.providers.alibaba_provider import AlibabaCloudProviderClient
from app.integrations.providers.aws_provider import AwsCloudProviderClient
from app.integrations.providers.azure_provider import AzureCloudProviderClient
from app.integrations.providers.gcp_provider import GcpCloudProviderClient
from app.integrations.providers.oci_provider import OciCloudProviderClient
from app.models.cloud_provider_account import CloudProviderAccount
from app.utils.crypto import encrypt_credentials
from app.utils.exceptions import ValidationAppError

AWS_CREDENTIALS = {"access_key_id": "testing", "secret_access_key": "testing"}


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- AWS test_connection() (moto + patched botocore errors) -----------------


@mock_aws
def test_aws_test_connection_succeeds():
    client = AwsCloudProviderClient(AWS_CREDENTIALS, "us-east-1")
    result = client.test_connection()
    assert result["provider"] == "aws"
    assert result["status"] == "success"
    assert result["account_id"].isdigit()
    assert result["principal"].startswith("arn:aws:")
    assert result["region"] == "us-east-1"


def _sts_error(code: str, message: str = "boom") -> botocore.exceptions.ClientError:
    return botocore.exceptions.ClientError({"Error": {"Code": code, "Message": message}}, "GetCallerIdentity")


def test_aws_test_connection_reports_invalid_access_key():
    client = AwsCloudProviderClient(AWS_CREDENTIALS, "us-east-1")
    with patch("boto3.client") as mock_client_factory:
        mock_client_factory.return_value.get_caller_identity.side_effect = _sts_error("InvalidClientTokenId")
        with pytest.raises(ValidationAppError) as exc_info:
            client.test_connection()
    assert exc_info.value.code == "AWS_INVALID_ACCESS_KEY"


def test_aws_test_connection_reports_invalid_secret_key():
    client = AwsCloudProviderClient(AWS_CREDENTIALS, "us-east-1")
    with patch("boto3.client") as mock_client_factory:
        mock_client_factory.return_value.get_caller_identity.side_effect = _sts_error("SignatureDoesNotMatch")
        with pytest.raises(ValidationAppError) as exc_info:
            client.test_connection()
    assert exc_info.value.code == "AWS_INVALID_SECRET_KEY"


def test_aws_test_connection_reports_access_denied():
    client = AwsCloudProviderClient(AWS_CREDENTIALS, "us-east-1")
    with patch("boto3.client") as mock_client_factory:
        mock_client_factory.return_value.get_caller_identity.side_effect = _sts_error("AccessDenied")
        with pytest.raises(ValidationAppError) as exc_info:
            client.test_connection()
    assert exc_info.value.code == "AWS_ACCESS_DENIED"


def test_aws_test_connection_reports_expired_session_token():
    client = AwsCloudProviderClient(AWS_CREDENTIALS, "us-east-1")
    with patch("boto3.client") as mock_client_factory:
        mock_client_factory.return_value.get_caller_identity.side_effect = _sts_error("ExpiredToken")
        with pytest.raises(ValidationAppError) as exc_info:
            client.test_connection()
    assert exc_info.value.code == "AWS_SESSION_TOKEN_EXPIRED"


def test_aws_test_connection_reports_network_error():
    client = AwsCloudProviderClient(AWS_CREDENTIALS, "us-east-1")
    with patch("boto3.client") as mock_client_factory:
        mock_client_factory.return_value.get_caller_identity.side_effect = botocore.exceptions.EndpointConnectionError(
            endpoint_url="https://sts.amazonaws.com"
        )
        with pytest.raises(ValidationAppError) as exc_info:
            client.test_connection()
    assert exc_info.value.code == "AWS_NETWORK_ERROR"


@mock_aws
def test_aws_test_connection_reports_invalid_region():
    client = AwsCloudProviderClient(AWS_CREDENTIALS, "not-a-real-region-1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.test_connection()
    assert exc_info.value.code == "AWS_REGION_INVALID"


def test_aws_test_connection_requires_credentials():
    client = AwsCloudProviderClient({}, "us-east-1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.test_connection()
    assert exc_info.value.code == "AWS_CREDENTIALS_INCOMPLETE"


# --- Azure/GCP/OCI/Alibaba test_connection() (generic base-class impl) ------


@patch("app.integrations.providers.azure_provider.ClientSecretCredential")
@patch("app.integrations.providers.azure_provider.SubscriptionClient")
def test_azure_test_connection_succeeds(mock_client_cls, _mock_cred):
    mock_client_cls.return_value.subscriptions.list_locations.return_value = [
        SimpleNamespace(name="eastus", display_name="East US"),
    ]
    mock_client_cls.return_value.subscriptions.get.return_value = SimpleNamespace(display_name="My Subscription")
    credentials = {
        "tenant_id": "fake-tenant",
        "client_id": "fake-client",
        "client_secret": "fake-secret",
        "subscription_id": "fake-sub",
    }
    client = AzureCloudProviderClient(credentials, "eastus")

    result = client.test_connection()

    assert result["provider"] == "azure"
    assert result["account_id"] == "fake-sub"
    assert result["account_alias"] == "My Subscription"
    assert result["principal"] == "fake-client"


@patch("app.integrations.providers.azure_provider.ClientSecretCredential")
@patch("app.integrations.providers.azure_provider.SubscriptionClient")
def test_azure_test_connection_rejects_bad_credentials(mock_client_cls, _mock_cred):
    mock_client_cls.return_value.subscriptions.list_locations.side_effect = ClientAuthenticationError("bad secret")
    credentials = {
        "tenant_id": "fake-tenant",
        "client_id": "fake-client",
        "client_secret": "wrong-secret",
        "subscription_id": "fake-sub",
    }
    client = AzureCloudProviderClient(credentials, "eastus")
    with pytest.raises(ValidationAppError) as exc_info:
        client.test_connection()
    assert exc_info.value.code == "AZURE_REGION_CREDENTIALS_REJECTED"


@patch("app.integrations.providers.azure_provider.ClientSecretCredential")
@patch("app.integrations.providers.azure_provider.SubscriptionClient")
def test_azure_test_connection_reports_invalid_region(mock_client_cls, _mock_cred):
    mock_client_cls.return_value.subscriptions.list_locations.return_value = [
        SimpleNamespace(name="eastus", display_name="East US"),
    ]
    credentials = {
        "tenant_id": "fake-tenant",
        "client_id": "fake-client",
        "client_secret": "fake-secret",
        "subscription_id": "fake-sub",
    }
    client = AzureCloudProviderClient(credentials, "not-a-real-region")
    with pytest.raises(ValidationAppError) as exc_info:
        client.test_connection()
    assert exc_info.value.code == "AZURE_REGION_INVALID"


GCP_SERVICE_ACCOUNT_INFO = {
    "type": "service_account",
    "project_id": "fake-project",
    "client_email": "svc@fake-project.iam.gserviceaccount.com",
}
GCP_CREDENTIALS = {"service_account_json": json.dumps(GCP_SERVICE_ACCOUNT_INFO)}


@patch("app.integrations.providers.gcp_provider.service_account")
@patch("app.integrations.providers.gcp_provider.compute_v1.RegionsClient")
def test_gcp_test_connection_succeeds(mock_client_cls, _mock_service_account):
    mock_client_cls.return_value.list.return_value = [SimpleNamespace(name="us-central1")]
    client = GcpCloudProviderClient(GCP_CREDENTIALS, "us-central1")

    result = client.test_connection()

    assert result["provider"] == "gcp"
    assert result["account_id"] == "fake-project"
    assert result["account_alias"] is None
    assert result["principal"] == "svc@fake-project.iam.gserviceaccount.com"


OCI_CREDENTIALS = {
    "user": "ocid1.user.oc1..fake",
    "tenancy": "ocid1.tenancy.oc1..fake",
    "fingerprint": "aa:bb:cc:dd",
    "key_content": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
}


@patch("app.integrations.providers.oci_provider.oci.identity.IdentityClient")
def test_oci_test_connection_succeeds(mock_client_cls):
    mock_client_cls.return_value.list_region_subscriptions.return_value = SimpleNamespace(
        data=[SimpleNamespace(region_name="us-ashburn-1", status="READY")]
    )
    mock_client_cls.return_value.get_tenancy.return_value = SimpleNamespace(data=SimpleNamespace(name="my-tenancy"))
    client = OciCloudProviderClient(OCI_CREDENTIALS, "us-ashburn-1")

    result = client.test_connection()

    assert result["provider"] == "oci"
    assert result["account_id"] == "ocid1.tenancy.oc1..fake"
    assert result["account_alias"] == "my-tenancy"
    assert result["principal"] == "ocid1.user.oc1..fake"


ALIBABA_CREDENTIALS = {"access_key_id": "fake-ak", "access_key_secret": "fake-sk"}


@patch("app.integrations.providers.alibaba_provider.EcsClient")
def test_alibaba_test_connection_succeeds(mock_client_cls):
    mock_client_cls.return_value.describe_regions.return_value = SimpleNamespace(
        body=SimpleNamespace(
            regions=SimpleNamespace(region=[SimpleNamespace(region_id="cn-hangzhou", local_name="China (Hangzhou)")])
        )
    )
    client = AlibabaCloudProviderClient(ALIBABA_CREDENTIALS, "cn-hangzhou")

    result = client.test_connection()

    assert result["provider"] == "alibaba"
    # Alibaba has no cheap STS-equivalent identity call wired up in this
    # pass - honestly disclosed as None rather than fabricated.
    assert result["account_id"] is None
    assert result["account_alias"] is None


# --- API endpoints -----------------------------------------------------


@mock_aws
def test_test_connection_endpoint_is_stateless(client, make_user_with_role, db_session):
    token = make_user_with_role("cred_op_a", "operator")
    response = client.post(
        "/api/v1/cloud-provider-accounts/test-connection",
        json={"provider": "aws", "region": "us-east-1", "credentials": AWS_CREDENTIALS},
        headers=_auth_header(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["account_id"].isdigit()

    # Never persisted anything.
    count = db_session.query(CloudProviderAccount).count()
    assert count == 0


@mock_aws
def test_test_connection_endpoint_reports_the_exact_reason(client, make_user_with_role):
    token = make_user_with_role("cred_op_b", "operator")
    with patch("boto3.client") as mock_client_factory:
        mock_client_factory.return_value.get_caller_identity.side_effect = _sts_error("SignatureDoesNotMatch")
        response = client.post(
            "/api/v1/cloud-provider-accounts/test-connection",
            json={"provider": "aws", "region": "us-east-1", "credentials": AWS_CREDENTIALS},
            headers=_auth_header(token),
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AWS_INVALID_SECRET_KEY"


@mock_aws
def test_validate_credentials_flips_the_flag_and_starts_monitoring(client, make_user_with_role, db_session):
    token = make_user_with_role("cred_op_c", "operator")
    created = client.post(
        "/api/v1/cloud-provider-accounts",
        json={
            "provider": "aws",
            "account_name": "cred-workflow-account",
            "region": "us-east-1",
            "credentials": AWS_CREDENTIALS,
        },
        headers=_auth_header(token),
    ).json()
    assert created["credentials_validated"] is False

    response = client.post(
        f"/api/v1/cloud-provider-accounts/{created['id']}/validate-credentials", headers=_auth_header(token)
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    db_session.expire_all()
    account = db_session.query(CloudProviderAccount).filter(CloudProviderAccount.id == created["id"]).one()
    assert account.credentials_validated is True
    assert account.credentials_validated_at is not None
    # The best-effort region sync fired as part of validation - real
    # monitoring data (available regions) is now populated immediately.
    assert account.available_regions != "[]"


def test_validate_credentials_reports_the_exact_reason_and_does_not_flip_the_flag(
    client, make_user_with_role, db_session
):
    token = make_user_with_role("cred_op_d", "operator")
    created = client.post(
        "/api/v1/cloud-provider-accounts",
        json={
            "provider": "aws",
            "account_name": "cred-workflow-bad-account",
            "region": "us-east-1",
            "credentials": {"access_key_id": "bad", "secret_access_key": "bad"},
        },
        headers=_auth_header(token),
    ).json()

    with patch("boto3.client") as mock_client_factory:
        mock_client_factory.return_value.get_caller_identity.side_effect = _sts_error("InvalidClientTokenId")
        response = client.post(
            f"/api/v1/cloud-provider-accounts/{created['id']}/validate-credentials", headers=_auth_header(token)
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AWS_INVALID_ACCESS_KEY"

    db_session.expire_all()
    account = db_session.query(CloudProviderAccount).filter(CloudProviderAccount.id == created["id"]).one()
    assert account.credentials_validated is False


def test_validate_credentials_rejects_a_non_owner(client, make_user_with_role, db_session):
    owner_token = make_user_with_role("cred_owner_e", "operator")
    other_token = make_user_with_role("cred_other_e", "operator")
    account = CloudProviderAccount(
        user_id=client.get("/api/v1/auth/me", headers=_auth_header(owner_token)).json()["id"],
        provider="aws",
        account_name="cred-workflow-owned",
        region="us-east-1",
        credentials_encrypted=encrypt_credentials(AWS_CREDENTIALS),
    )
    db_session.add(account)
    db_session.commit()

    response = client.post(
        f"/api/v1/cloud-provider-accounts/{account.id}/validate-credentials", headers=_auth_header(other_token)
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_YOUR_CLOUD_ACCOUNT"


@mock_aws
def test_replacing_credentials_resets_the_validated_flag(client, make_user_with_role, db_session):
    token = make_user_with_role("cred_op_f", "operator")
    created = client.post(
        "/api/v1/cloud-provider-accounts",
        json={
            "provider": "aws",
            "account_name": "cred-workflow-reset",
            "region": "us-east-1",
            "credentials": AWS_CREDENTIALS,
        },
        headers=_auth_header(token),
    ).json()
    client.post(f"/api/v1/cloud-provider-accounts/{created['id']}/validate-credentials", headers=_auth_header(token))

    response = client.put(
        f"/api/v1/cloud-provider-accounts/{created['id']}",
        json={"credentials": {"access_key_id": "new-key", "secret_access_key": "new-secret"}},
        headers=_auth_header(token),
    )
    assert response.status_code == 200
    assert response.json()["credentials_validated"] is False
