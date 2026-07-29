"""Unit tests for Phase 25D's OCI provisioning (deploy/destroy for compute/
storage/networking) - patches the real `oci` SDK client classes directly,
the same pattern test_oci_resource_inventory.py already establishes (no
OCI emulator available). Every test here runs exclusively against mocked
clients - none is capable of touching a real OCI tenancy."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.integrations.providers.oci_provider import OciCloudProviderClient
from app.utils.exceptions import ValidationAppError

CREDENTIALS = {
    "user": "ocid1.user.oc1..fake",
    "tenancy": "ocid1.tenancy.oc1..fake",
    "fingerprint": "aa:bb:cc:dd",
    "key_content": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
}
COMPUTE_SPEC = {
    "image_id": "ocid1.image.oc1..fake",
    "availability_domain": "AD-1",
    "subnet_id": "ocid1.subnet.oc1..fake",
}


@patch("app.integrations.providers.oci_provider.oci.core.ComputeClient")
def test_deploy_and_destroy_compute(mock_client_cls):
    mock_client_cls.return_value.launch_instance.return_value = SimpleNamespace(
        data=SimpleNamespace(
            id="ocid1.instance.oc1..fake", display_name="my-instance", lifecycle_state="PROVISIONING",
            time_created="2026-01-01T00:00:00Z",
        )
    )
    client = OciCloudProviderClient(CREDENTIALS, "us-ashburn-1")

    result = client.deploy("us-ashburn-1", "compute", {**COMPUTE_SPEC, "name": "my-instance"})
    assert result["name"] == "my-instance"
    assert result["type"] == "VM.Standard.E2.1.Micro"

    client.destroy("us-ashburn-1", "compute", result["id"])
    mock_client_cls.return_value.terminate_instance.assert_called_once_with("ocid1.instance.oc1..fake")


def test_deploy_compute_requires_full_spec():
    client = OciCloudProviderClient(CREDENTIALS, "us-ashburn-1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.deploy("us-ashburn-1", "compute", {})
    assert exc_info.value.code == "OCI_DEPLOY_SPEC_INCOMPLETE"


@patch("app.integrations.providers.oci_provider.oci.object_storage.ObjectStorageClient")
def test_deploy_and_destroy_storage(mock_client_cls):
    mock_client_cls.return_value.get_namespace.return_value = SimpleNamespace(data="my-namespace")
    mock_client_cls.return_value.create_bucket.return_value = SimpleNamespace(
        data=SimpleNamespace(name="my-bucket", time_created="2026-01-01T00:00:00Z")
    )
    client = OciCloudProviderClient(CREDENTIALS, "us-ashburn-1")

    result = client.deploy("us-ashburn-1", "storage", {"name": "my-bucket"})
    assert result["name"] == "my-bucket"

    client.destroy("us-ashburn-1", "storage", result["id"])
    mock_client_cls.return_value.delete_bucket.assert_called_once_with("my-namespace", "my-bucket")


def test_deploy_storage_requires_name():
    client = OciCloudProviderClient(CREDENTIALS, "us-ashburn-1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.deploy("us-ashburn-1", "storage", {})
    assert exc_info.value.code == "OCI_DEPLOY_SPEC_INCOMPLETE"


@patch("app.integrations.providers.oci_provider.oci.core.VirtualNetworkClient")
def test_deploy_and_destroy_networking(mock_client_cls):
    mock_client_cls.return_value.create_vcn.return_value = SimpleNamespace(
        data=SimpleNamespace(
            id="ocid1.vcn.oc1..fake", display_name="my-vcn", lifecycle_state="PROVISIONING",
            time_created="2026-01-01T00:00:00Z",
        )
    )
    client = OciCloudProviderClient(CREDENTIALS, "us-ashburn-1")

    result = client.deploy("us-ashburn-1", "networking", {"name": "my-vcn"})
    assert result["name"] == "my-vcn"

    client.destroy("us-ashburn-1", "networking", result["id"])
    mock_client_cls.return_value.delete_vcn.assert_called_once_with("ocid1.vcn.oc1..fake")
