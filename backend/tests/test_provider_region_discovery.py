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
import pytest
from azure.core.exceptions import ClientAuthenticationError
from google.api_core.exceptions import PermissionDenied
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
    assert exc_info.value.code == "AZURE_REGION_DISCOVERY_FAILED"


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
    assert exc_info.value.code == "GCP_REGION_DISCOVERY_FAILED"


# --- provider_factory -------------------------------------------------------


def test_provider_factory_supports_every_registered_provider():
    assert supported_providers() == ["alibaba", "aws", "azure", "gcp", "oci"]


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
