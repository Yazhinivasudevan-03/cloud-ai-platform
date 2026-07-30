"""Unit tests for Phase 25's CloudProviderClient adapters' list_regions()/
list_projects() - the genuinely new real API calls this phase adds on top
of the already-real monitoring/cost fetchers. AWS is verified against
moto's real EC2 emulation (a faithful boto3 request/response path, same
justification as test_cloud_sync.py); Azure/GCP patch their SDK clients
directly, mirroring test_azure_monitor.py/test_gcp_monitoring.py's own
established pattern (no comparable emulator available for either)."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import boto3
import botocore.exceptions
import pytest
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError, ServiceRequestError
from google.api_core.exceptions import PermissionDenied, ServiceUnavailable, TooManyRequests
from moto import mock_aws

from app.integrations.provider_factory import get_cloud_provider_client, supported_providers
from app.integrations.providers.aws_provider import AwsCloudProviderClient
from app.integrations.providers.azure_provider import AzureCloudProviderClient
from app.integrations.providers.gcp_provider import GcpCloudProviderClient
from app.utils.exceptions import ValidationAppError


# --- AWS (moto) -----------------------------------------------------------


@mock_aws
def test_aws_list_regions_returns_real_ec2_regions():
    client = AwsCloudProviderClient(
        {"access_key_id": "testing", "secret_access_key": "testing"}, "us-east-1"
    )
    regions = client.list_regions()

    region_ids = {r["id"] for r in regions}
    assert "us-east-1" in region_ids
    assert "eu-west-2" in region_ids
    # Every entry has a real display name (either a curated label or, at
    # minimum, an honest fallback to its own id - never blank/fabricated).
    assert all(r["display_name"] for r in regions)


def test_aws_list_regions_requires_credentials():
    client = AwsCloudProviderClient({}, "us-east-1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "AWS_CREDENTIALS_INCOMPLETE"


@mock_aws
def test_aws_list_projects_returns_real_account_id():
    client = AwsCloudProviderClient(
        {"access_key_id": "testing", "secret_access_key": "testing"}, "us-east-1"
    )
    projects = client.list_projects()
    assert len(projects) == 1
    assert projects[0].isdigit()


# --- AWS region-discovery error taxonomy (Phase 25E) -----------------------
# Moto doesn't validate credentials or simulate throttling/outages, so these
# scenarios patch boto3.client directly, mirroring the established pattern
# already used for the same purpose in test_aws_cloudwatch.py/
# test_aws_cost_explorer.py.


def _client_error(code: str, message: str = "boom") -> botocore.exceptions.ClientError:
    return botocore.exceptions.ClientError({"Error": {"Code": code, "Message": message}}, "DescribeRegions")


def test_aws_list_regions_reports_expired_credentials():
    client = AwsCloudProviderClient({"access_key_id": "x", "secret_access_key": "y"}, "us-east-1")
    with patch("boto3.client") as mock_client_factory:
        mock_client_factory.return_value.describe_regions.side_effect = _client_error("ExpiredToken")
        with pytest.raises(ValidationAppError) as exc_info:
            client.list_regions()
    assert exc_info.value.code == "AWS_REGION_CREDENTIALS_EXPIRED"


def test_aws_list_regions_reports_access_denied():
    client = AwsCloudProviderClient({"access_key_id": "x", "secret_access_key": "y"}, "us-east-1")
    with patch("boto3.client") as mock_client_factory:
        mock_client_factory.return_value.describe_regions.side_effect = _client_error("UnauthorizedOperation")
        with pytest.raises(ValidationAppError) as exc_info:
            client.list_regions()
    assert exc_info.value.code == "AWS_REGION_ACCESS_DENIED"


def test_aws_list_regions_reports_throttled_after_retries_exhausted():
    client = AwsCloudProviderClient({"access_key_id": "x", "secret_access_key": "y"}, "us-east-1")
    with patch("boto3.client") as mock_client_factory:
        mock_client_factory.return_value.describe_regions.side_effect = _client_error("Throttling")
        with pytest.raises(ValidationAppError) as exc_info:
            client.list_regions()
    assert exc_info.value.code == "AWS_REGION_THROTTLED"
    # 3 attempts (the configured stop_after_attempt) prove the retry
    # actually ran, not just that failure was eventually reported.
    assert mock_client_factory.return_value.describe_regions.call_count == 3


def test_aws_list_regions_retries_a_transient_error_then_succeeds():
    client = AwsCloudProviderClient({"access_key_id": "x", "secret_access_key": "y"}, "us-east-1")
    success_response = {"Regions": [{"RegionName": "us-east-1"}]}
    with patch("boto3.client") as mock_client_factory:
        mock_client_factory.return_value.describe_regions.side_effect = [
            _client_error("Throttling"),
            success_response,
        ]
        regions = client.list_regions()
    assert regions == [{"id": "us-east-1", "display_name": "US East (N. Virginia)"}]
    assert mock_client_factory.return_value.describe_regions.call_count == 2


def test_aws_list_regions_reports_provider_outage():
    client = AwsCloudProviderClient({"access_key_id": "x", "secret_access_key": "y"}, "us-east-1")
    with patch("boto3.client") as mock_client_factory:
        mock_client_factory.return_value.describe_regions.side_effect = _client_error("ServiceUnavailable")
        with pytest.raises(ValidationAppError) as exc_info:
            client.list_regions()
    assert exc_info.value.code == "AWS_REGION_PROVIDER_OUTAGE"


def test_aws_list_regions_reports_timeout():
    client = AwsCloudProviderClient({"access_key_id": "x", "secret_access_key": "y"}, "us-east-1")
    with patch("boto3.client") as mock_client_factory:
        mock_client_factory.return_value.describe_regions.side_effect = botocore.exceptions.ConnectTimeoutError(
            endpoint_url="https://ec2.us-east-1.amazonaws.com"
        )
        with pytest.raises(ValidationAppError) as exc_info:
            client.list_regions()
    assert exc_info.value.code == "AWS_REGION_TIMEOUT"


def test_aws_list_regions_reports_network_unreachable():
    client = AwsCloudProviderClient({"access_key_id": "x", "secret_access_key": "y"}, "us-east-1")
    with patch("boto3.client") as mock_client_factory:
        mock_client_factory.return_value.describe_regions.side_effect = botocore.exceptions.EndpointConnectionError(
            endpoint_url="https://ec2.us-east-1.amazonaws.com"
        )
        with pytest.raises(ValidationAppError) as exc_info:
            client.list_regions()
    assert exc_info.value.code == "AWS_REGION_NETWORK_UNREACHABLE"


def test_aws_list_regions_reports_no_regions_returned():
    client = AwsCloudProviderClient({"access_key_id": "x", "secret_access_key": "y"}, "us-east-1")
    with patch("boto3.client") as mock_client_factory:
        mock_client_factory.return_value.describe_regions.return_value = {"Regions": []}
        with pytest.raises(ValidationAppError) as exc_info:
            client.list_regions()
    assert exc_info.value.code == "AWS_REGION_NO_REGIONS_RETURNED"


# --- Azure (patched SDK client) -------------------------------------------

AZURE_CREDENTIALS = {
    "tenant_id": "fake-tenant",
    "client_id": "fake-client",
    "client_secret": "fake-secret",
    "subscription_id": "fake-sub",
}


def _fake_location(name: str, display_name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name, display_name=display_name)


@patch("app.integrations.providers.azure_provider.ClientSecretCredential")
@patch("app.integrations.providers.azure_provider.SubscriptionClient")
def test_azure_list_regions_parses_real_locations(mock_client_cls, _mock_cred):
    mock_client_cls.return_value.subscriptions.list_locations.return_value = [
        _fake_location("eastus", "East US"),
        _fake_location("uksouth", "UK South"),
    ]
    client = AzureCloudProviderClient(AZURE_CREDENTIALS, "eastus")

    regions = client.list_regions()

    assert regions == [
        {"id": "eastus", "display_name": "East US"},
        {"id": "uksouth", "display_name": "UK South"},
    ]


def test_azure_list_regions_requires_full_credentials():
    client = AzureCloudProviderClient({"tenant_id": "x"}, "eastus")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "AZURE_CREDENTIALS_INCOMPLETE"


@patch("app.integrations.providers.azure_provider.ClientSecretCredential")
@patch("app.integrations.providers.azure_provider.SubscriptionClient")
def test_azure_list_regions_wraps_bad_credentials(mock_client_cls, _mock_cred):
    mock_client_cls.return_value.subscriptions.list_locations.side_effect = ClientAuthenticationError(
        "invalid client secret"
    )
    client = AzureCloudProviderClient(AZURE_CREDENTIALS, "eastus")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "AZURE_REGION_CREDENTIALS_REJECTED"


@patch("app.integrations.providers.azure_provider.ClientSecretCredential")
@patch("app.integrations.providers.azure_provider.SubscriptionClient")
def test_azure_list_regions_reports_throttled_after_retries_exhausted(mock_client_cls, _mock_cred):
    error = HttpResponseError(message="too many requests")
    error.status_code = 429
    mock_client_cls.return_value.subscriptions.list_locations.side_effect = error
    client = AzureCloudProviderClient(AZURE_CREDENTIALS, "eastus")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "AZURE_REGION_THROTTLED"
    assert mock_client_cls.return_value.subscriptions.list_locations.call_count == 3


@patch("app.integrations.providers.azure_provider.ClientSecretCredential")
@patch("app.integrations.providers.azure_provider.SubscriptionClient")
def test_azure_list_regions_reports_provider_outage(mock_client_cls, _mock_cred):
    error = HttpResponseError(message="internal error")
    error.status_code = 503
    mock_client_cls.return_value.subscriptions.list_locations.side_effect = error
    client = AzureCloudProviderClient(AZURE_CREDENTIALS, "eastus")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "AZURE_REGION_PROVIDER_OUTAGE"


@patch("app.integrations.providers.azure_provider.ClientSecretCredential")
@patch("app.integrations.providers.azure_provider.SubscriptionClient")
def test_azure_list_regions_reports_network_unreachable(mock_client_cls, _mock_cred):
    mock_client_cls.return_value.subscriptions.list_locations.side_effect = ServiceRequestError("DNS failure")
    client = AzureCloudProviderClient(AZURE_CREDENTIALS, "eastus")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "AZURE_REGION_NETWORK_UNREACHABLE"


@patch("app.integrations.providers.azure_provider.ClientSecretCredential")
@patch("app.integrations.providers.azure_provider.SubscriptionClient")
def test_azure_list_regions_reports_no_regions_returned(mock_client_cls, _mock_cred):
    mock_client_cls.return_value.subscriptions.list_locations.return_value = []
    client = AzureCloudProviderClient(AZURE_CREDENTIALS, "eastus")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "AZURE_REGION_NO_REGIONS_RETURNED"


# --- GCP (patched SDK client) ----------------------------------------------

GCP_SERVICE_ACCOUNT_INFO = {"type": "service_account", "project_id": "fake-project"}
GCP_CREDENTIALS = {"service_account_json": json.dumps(GCP_SERVICE_ACCOUNT_INFO)}


def _fake_region(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


@patch("app.integrations.providers.gcp_provider.service_account")
@patch("app.integrations.providers.gcp_provider.compute_v1.RegionsClient")
def test_gcp_list_regions_parses_real_regions(mock_client_cls, _mock_service_account):
    mock_client_cls.return_value.list.return_value = [
        _fake_region("us-central1"),
        _fake_region("europe-west9"),  # not in the curated display-name table
    ]
    client = GcpCloudProviderClient(GCP_CREDENTIALS, "us-central1")

    regions = client.list_regions()

    assert regions[0] == {"id": "us-central1", "display_name": "Iowa"}
    # Unmapped region still appears, using its own id as a fallback label -
    # never hidden just because it isn't in the curated table.
    assert regions[1] == {"id": "europe-west9", "display_name": "europe-west9"}


def test_gcp_list_regions_requires_service_account_json():
    client = GcpCloudProviderClient({}, "us-central1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "GCP_CREDENTIALS_INCOMPLETE"


@patch("app.integrations.providers.gcp_provider.service_account")
@patch("app.integrations.providers.gcp_provider.compute_v1.RegionsClient")
def test_gcp_list_regions_wraps_permission_denied(mock_client_cls, _mock_service_account):
    mock_client_cls.return_value.list.side_effect = PermissionDenied("no access")
    client = GcpCloudProviderClient(GCP_CREDENTIALS, "us-central1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "GCP_REGION_ACCESS_DENIED"


@patch("app.integrations.providers.gcp_provider.service_account")
@patch("app.integrations.providers.gcp_provider.compute_v1.RegionsClient")
def test_gcp_list_regions_reports_throttled_after_retries_exhausted(mock_client_cls, _mock_service_account):
    mock_client_cls.return_value.list.side_effect = TooManyRequests("rate limited")
    client = GcpCloudProviderClient(GCP_CREDENTIALS, "us-central1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "GCP_REGION_THROTTLED"
    assert mock_client_cls.return_value.list.call_count == 3


@patch("app.integrations.providers.gcp_provider.service_account")
@patch("app.integrations.providers.gcp_provider.compute_v1.RegionsClient")
def test_gcp_list_regions_reports_provider_outage(mock_client_cls, _mock_service_account):
    mock_client_cls.return_value.list.side_effect = ServiceUnavailable("down for maintenance")
    client = GcpCloudProviderClient(GCP_CREDENTIALS, "us-central1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "GCP_REGION_PROVIDER_OUTAGE"


@patch("app.integrations.providers.gcp_provider.service_account")
@patch("app.integrations.providers.gcp_provider.compute_v1.RegionsClient")
def test_gcp_list_regions_reports_no_regions_returned(mock_client_cls, _mock_service_account):
    mock_client_cls.return_value.list.return_value = []
    client = GcpCloudProviderClient(GCP_CREDENTIALS, "us-central1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "GCP_REGION_NO_REGIONS_RETURNED"


# --- provider_factory -------------------------------------------------------


def test_provider_factory_supports_every_registered_provider():
    assert supported_providers() == ["alibaba", "aws", "azure", "digitalocean", "gcp", "ibm", "oci"]


def test_provider_factory_rejects_unknown_provider():
    with pytest.raises(ValidationAppError) as exc_info:
        get_cloud_provider_client("oracle", {}, "us-east-1")
    assert exc_info.value.code == "CLOUD_PROVIDER_NOT_SUPPORTED"


def test_provider_factory_returns_the_right_adapter_type():
    client = get_cloud_provider_client(
        "aws", {"access_key_id": "x", "secret_access_key": "y"}, "us-east-1"
    )
    assert isinstance(client, AwsCloudProviderClient)
    assert client.provider_name == "aws"
