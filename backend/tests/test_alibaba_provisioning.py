"""Unit tests for Phase 25D's Alibaba Cloud provisioning (deploy/destroy
for compute/storage/networking) - patches the real Tea-based SDK client
classes (+ oss2 for OSS) directly, the same pattern
test_alibaba_resource_inventory.py already establishes (no Alibaba Cloud
emulator available). Every test here runs exclusively against mocked
clients - none is capable of touching a real Alibaba Cloud account."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.integrations.providers.alibaba_provider import AlibabaCloudProviderClient
from app.utils.exceptions import ValidationAppError

CREDENTIALS = {"access_key_id": "fake-ak", "access_key_secret": "fake-sk"}
COMPUTE_SPEC = {"image_id": "img-fake", "security_group_id": "sg-fake"}


@patch("app.integrations.providers.alibaba_provider.EcsClient")
def test_deploy_and_destroy_compute(mock_client_cls):
    mock_client_cls.return_value.create_instance.return_value = SimpleNamespace(
        body=SimpleNamespace(instance_id="i-fake123")
    )
    client = AlibabaCloudProviderClient(CREDENTIALS, "cn-hangzhou")

    result = client.deploy("cn-hangzhou", "compute", {**COMPUTE_SPEC, "name": "my-ecs"})
    assert result["name"] == "my-ecs"
    assert result["type"] == "ecs.t5-lc1m1.small"
    assert result["id"] == "i-fake123"

    client.destroy("cn-hangzhou", "compute", result["id"])
    mock_client_cls.return_value.delete_instance.assert_called_once()


def test_deploy_compute_requires_image_and_security_group():
    client = AlibabaCloudProviderClient(CREDENTIALS, "cn-hangzhou")
    with pytest.raises(ValidationAppError) as exc_info:
        client.deploy("cn-hangzhou", "compute", {})
    assert exc_info.value.code == "ALIBABA_DEPLOY_SPEC_INCOMPLETE"


@patch("app.integrations.providers.alibaba_provider.oss2.Bucket")
def test_deploy_and_destroy_storage(mock_bucket_cls):
    client = AlibabaCloudProviderClient(CREDENTIALS, "cn-hangzhou")

    result = client.deploy("cn-hangzhou", "storage", {"name": "my-oss-bucket"})
    assert result["id"] == "my-oss-bucket"
    mock_bucket_cls.return_value.create_bucket.assert_called_once()

    client.destroy("cn-hangzhou", "storage", result["id"])
    mock_bucket_cls.return_value.delete_bucket.assert_called_once()


def test_deploy_storage_requires_name():
    client = AlibabaCloudProviderClient(CREDENTIALS, "cn-hangzhou")
    with pytest.raises(ValidationAppError) as exc_info:
        client.deploy("cn-hangzhou", "storage", {})
    assert exc_info.value.code == "ALIBABA_DEPLOY_SPEC_INCOMPLETE"


@patch("app.integrations.providers.alibaba_provider.VpcClient")
def test_deploy_and_destroy_networking(mock_client_cls):
    mock_client_cls.return_value.create_vpc.return_value = SimpleNamespace(body=SimpleNamespace(vpc_id="vpc-fake123"))
    client = AlibabaCloudProviderClient(CREDENTIALS, "cn-hangzhou")

    result = client.deploy("cn-hangzhou", "networking", {"name": "my-vpc"})
    assert result["name"] == "my-vpc"
    assert result["id"] == "vpc-fake123"

    client.destroy("cn-hangzhou", "networking", result["id"])
    mock_client_cls.return_value.delete_vpc.assert_called_once()
