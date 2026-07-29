"""Unit tests for Phase 25D's AWS provisioning (deploy/destroy for compute/
storage/networking) - verified against moto's real EC2/S3 emulation, the
same faithful boto3 request/response path already relied on elsewhere in
this project. Every test here runs exclusively against moto - none is
capable of touching a real AWS account."""
import pytest
from moto import mock_aws

from app.integrations.providers.aws_provider import AwsCloudProviderClient
from app.utils.exceptions import ValidationAppError

FAKE_CREDENTIALS = {"access_key_id": "testing", "secret_access_key": "testing"}


@mock_aws
def test_deploy_and_destroy_compute():
    client = AwsCloudProviderClient(FAKE_CREDENTIALS, "us-east-1")

    result = client.deploy("us-east-1", "compute", {"image_id": "ami-12345678", "name": "test-vm"})
    assert result["name"] == "test-vm"
    assert result["type"] == "t3.micro"
    assert result["region"] == "us-east-1"

    client.destroy("us-east-1", "compute", result["id"])
    resources = client.list_resources("us-east-1")
    assert all(r["status"] == "terminated" for r in resources if r["id"] == result["id"])


def test_deploy_compute_requires_image_id():
    client = AwsCloudProviderClient(FAKE_CREDENTIALS, "us-east-1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.deploy("us-east-1", "compute", {})
    assert exc_info.value.code == "AWS_DEPLOY_SPEC_INCOMPLETE"


@mock_aws
def test_deploy_and_destroy_storage():
    client = AwsCloudProviderClient(FAKE_CREDENTIALS, "us-east-1")

    result = client.deploy("us-east-1", "storage", {"name": "my-real-provisioned-bucket"})
    assert result["id"] == "my-real-provisioned-bucket"
    assert result["type"] == "s3_bucket"

    client.destroy("us-east-1", "storage", result["id"])
    buckets = client.list_storage("us-east-1")
    assert all(b["id"] != result["id"] for b in buckets)


def test_deploy_storage_requires_name():
    client = AwsCloudProviderClient(FAKE_CREDENTIALS, "us-east-1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.deploy("us-east-1", "storage", {})
    assert exc_info.value.code == "AWS_DEPLOY_SPEC_INCOMPLETE"


@mock_aws
def test_deploy_and_destroy_networking():
    client = AwsCloudProviderClient(FAKE_CREDENTIALS, "us-east-1")

    result = client.deploy("us-east-1", "networking", {"cidr_block": "10.1.0.0/16", "name": "test-vpc"})
    assert result["name"] == "test-vpc"
    assert result["type"] == "vpc"

    client.destroy("us-east-1", "networking", result["id"])
    vpcs = client.list_networking("us-east-1")
    assert all(v["id"] != result["id"] for v in vpcs)


def test_deploy_rejects_an_unsupported_resource_type():
    client = AwsCloudProviderClient(FAKE_CREDENTIALS, "us-east-1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.deploy("us-east-1", "clusters", {})
    assert "PROVISIONING" in exc_info.value.code
