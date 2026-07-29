"""Unit tests for Phase 25D's GCP provisioning (deploy/destroy for compute/
storage/networking) - patches the real google-cloud-* SDK clients directly,
the same pattern test_gcp_resource_inventory.py already establishes (no GCP
emulator available). Every test here runs exclusively against mocked
clients - none is capable of touching a real GCP project."""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.integrations.providers.gcp_provider import GcpCloudProviderClient
from app.utils.exceptions import ValidationAppError

FAKE_SERVICE_ACCOUNT_INFO = {"type": "service_account", "project_id": "fake-project"}
CREDENTIALS = {"service_account_json": json.dumps(FAKE_SERVICE_ACCOUNT_INFO)}


def _operation():
    op = MagicMock()
    op.result.return_value = None
    return op


@patch("app.integrations.providers.gcp_provider.service_account")
@patch("app.integrations.providers.gcp_provider.compute_v1.InstancesClient")
def test_deploy_and_destroy_compute(mock_client_cls, _mock_service_account):
    mock_client_cls.return_value.insert.return_value = _operation()
    mock_client_cls.return_value.delete.return_value = _operation()
    client = GcpCloudProviderClient(CREDENTIALS, "us-central1")

    result = client.deploy("us-central1", "compute", {"image": "projects/debian-cloud/global/images/family/debian-12", "name": "my-vm"})

    assert result["name"] == "my-vm"
    assert result["type"] == "e2-micro"
    mock_client_cls.return_value.insert.assert_called_once()

    client.destroy("us-central1", "compute", result["id"])
    mock_client_cls.return_value.delete.assert_called_once()


def test_deploy_compute_requires_image():
    client = GcpCloudProviderClient(CREDENTIALS, "us-central1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.deploy("us-central1", "compute", {})
    assert exc_info.value.code == "GCP_DEPLOY_SPEC_INCOMPLETE"


@patch("app.integrations.providers.gcp_provider.storage.Client")
@patch("app.integrations.providers.gcp_provider.service_account")
def test_deploy_and_destroy_storage(_mock_service_account, mock_storage_client_cls):
    client = GcpCloudProviderClient(CREDENTIALS, "us-central1")

    result = client.deploy("us-central1", "storage", {"name": "my-provisioned-bucket"})
    assert result["id"] == "my-provisioned-bucket"
    mock_storage_client_cls.return_value.create_bucket.assert_called_once_with("my-provisioned-bucket", location="us-central1")

    client.destroy("us-central1", "storage", result["id"])
    mock_storage_client_cls.return_value.bucket.assert_called_once_with("my-provisioned-bucket")


def test_deploy_storage_requires_name():
    client = GcpCloudProviderClient(CREDENTIALS, "us-central1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.deploy("us-central1", "storage", {})
    assert exc_info.value.code == "GCP_DEPLOY_SPEC_INCOMPLETE"


@patch("app.integrations.providers.gcp_provider.service_account")
@patch("app.integrations.providers.gcp_provider.compute_v1.NetworksClient")
def test_deploy_and_destroy_networking(mock_client_cls, _mock_service_account):
    mock_client_cls.return_value.insert.return_value = _operation()
    mock_client_cls.return_value.delete.return_value = _operation()
    client = GcpCloudProviderClient(CREDENTIALS, "us-central1")

    result = client.deploy("us-central1", "networking", {"name": "my-network"})
    assert result["name"] == "my-network"
    mock_client_cls.return_value.insert.assert_called_once()

    client.destroy("us-central1", "networking", result["id"])
    mock_client_cls.return_value.delete.assert_called_once()
