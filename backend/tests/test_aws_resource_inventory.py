"""Unit tests for Phase 25C's AWS resource inventory (compute/clusters/
databases/storage/networking) - verified against moto's real EC2/EKS/RDS/S3
emulation, the same faithful boto3 request/response path already relied on
elsewhere in this project."""
import boto3
import pytest
from moto import mock_aws

from app.integrations.providers.aws_provider import AwsCloudProviderClient

FAKE_CREDENTIALS = {"access_key_id": "testing", "secret_access_key": "testing"}


@mock_aws
def test_list_resources_returns_real_ec2_instances():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    ec2.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1, InstanceType="t2.micro")

    client = AwsCloudProviderClient(FAKE_CREDENTIALS, "us-east-1")
    resources = client.list_resources("us-east-1")

    assert len(resources) == 1
    assert resources[0]["type"] == "t2.micro"
    assert resources[0]["region"] == "us-east-1"
    assert resources[0]["status"] in ("pending", "running")


@mock_aws
def test_list_clusters_returns_real_eks_clusters():
    eks = boto3.client("eks", region_name="us-east-1")
    eks.create_cluster(
        name="my-cluster",
        roleArn="arn:aws:iam::123456789012:role/eks-role",
        resourcesVpcConfig={"subnetIds": ["subnet-12345"]},
    )

    client = AwsCloudProviderClient(FAKE_CREDENTIALS, "us-east-1")
    clusters = client.list_clusters("us-east-1")

    assert len(clusters) == 1
    assert clusters[0]["name"] == "my-cluster"
    assert clusters[0]["type"] == "eks"


@mock_aws
def test_list_databases_returns_real_rds_instances():
    rds = boto3.client("rds", region_name="us-east-1")
    rds.create_db_instance(
        DBInstanceIdentifier="my-db",
        Engine="mysql",
        DBInstanceClass="db.t3.micro",
        MasterUsername="admin",
        MasterUserPassword="password123",
        AllocatedStorage=20,
    )

    client = AwsCloudProviderClient(FAKE_CREDENTIALS, "us-east-1")
    databases = client.list_databases("us-east-1")

    assert len(databases) == 1
    assert databases[0]["id"] == "my-db"
    assert databases[0]["type"] == "mysql"


@mock_aws
def test_list_storage_returns_real_s3_buckets():
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="my-real-bucket")

    client = AwsCloudProviderClient(FAKE_CREDENTIALS, "us-east-1")
    buckets = client.list_storage("us-east-1")

    assert len(buckets) == 1
    assert buckets[0]["id"] == "my-real-bucket"
    assert buckets[0]["type"] == "s3_bucket"


@mock_aws
def test_list_networking_returns_real_vpcs():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    ec2.create_vpc(CidrBlock="10.0.0.0/16")

    client = AwsCloudProviderClient(FAKE_CREDENTIALS, "us-east-1")
    vpcs = client.list_networking("us-east-1")

    # The default VPC moto seeds plus the one just created.
    assert len(vpcs) >= 1
    assert all(v["type"] == "vpc" for v in vpcs)


def test_inventory_methods_require_credentials():
    client = AwsCloudProviderClient({}, "us-east-1")
    with pytest.raises(Exception):
        client.list_resources("us-east-1")
