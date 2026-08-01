"""Unit tests for Phase 25C's AWS resource inventory (compute/clusters/
databases/storage/networking) - verified against moto's real EC2/EKS/RDS/S3
emulation, the same faithful boto3 request/response path already relied on
elsewhere in this project."""
import json

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


# --- Phase 29: broader inventory categories + detailed EC2 shape ------------


@mock_aws
def test_list_ec2_instances_detailed_returns_az_and_ip_fields():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    ec2.run_instances(
        ImageId="ami-12345678",
        MinCount=1,
        MaxCount=1,
        InstanceType="t2.micro",
        TagSpecifications=[{"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": "web-1"}]}],
    )

    client = AwsCloudProviderClient(FAKE_CREDENTIALS, "us-east-1")
    instances = client.list_ec2_instances_detailed("us-east-1")

    assert len(instances) == 1
    instance = instances[0]
    assert instance["name"] == "web-1"
    assert instance["instance_type"] == "t2.micro"
    assert instance["availability_zone"]
    assert instance["private_ip"]
    assert instance["tags"] == {"Name": "web-1"}


@mock_aws
def test_list_ecs_clusters_returns_real_clusters():
    ecs = boto3.client("ecs", region_name="us-east-1")
    ecs.create_cluster(clusterName="my-ecs-cluster")

    client = AwsCloudProviderClient(FAKE_CREDENTIALS, "us-east-1")
    clusters = client.list_ecs_clusters("us-east-1")

    assert len(clusters) == 1
    assert clusters[0]["name"] == "my-ecs-cluster"
    assert clusters[0]["type"] == "ecs_cluster"


@mock_aws
def test_list_serverless_functions_returns_real_lambda_functions():
    iam = boto3.client("iam", region_name="us-east-1")
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}
        ],
    }
    role_arn = iam.create_role(
        RoleName="lambda-role", AssumeRolePolicyDocument=json.dumps(trust_policy)
    )["Role"]["Arn"]

    lam = boto3.client("lambda", region_name="us-east-1")
    lam.create_function(
        FunctionName="my-function",
        Runtime="python3.12",
        Role=role_arn,
        Handler="handler.main",
        Code={"ZipFile": b"fake code"},
    )

    client = AwsCloudProviderClient(FAKE_CREDENTIALS, "us-east-1")
    functions = client.list_serverless_functions("us-east-1")

    assert len(functions) == 1
    assert functions[0]["name"] == "my-function"
    assert functions[0]["type"] == "python3.12"


@mock_aws
def test_list_volumes_returns_real_ebs_volumes():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    ec2.create_volume(AvailabilityZone="us-east-1a", Size=10)

    client = AwsCloudProviderClient(FAKE_CREDENTIALS, "us-east-1")
    volumes = client.list_volumes("us-east-1")

    assert len(volumes) == 1
    assert volumes[0]["status"] in ("available", "creating", "in-use")


@mock_aws
def test_list_load_balancers_returns_real_load_balancers():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]["VpcId"]
    subnet = ec2.create_subnet(VpcId=vpc, CidrBlock="10.0.0.0/24", AvailabilityZone="us-east-1a")["Subnet"][
        "SubnetId"
    ]
    elbv2 = boto3.client("elbv2", region_name="us-east-1")
    elbv2.create_load_balancer(Name="my-lb", Subnets=[subnet])

    client = AwsCloudProviderClient(FAKE_CREDENTIALS, "us-east-1")
    load_balancers = client.list_load_balancers("us-east-1")

    assert len(load_balancers) == 1
    assert load_balancers[0]["name"] == "my-lb"


@mock_aws
def test_list_scaling_groups_returns_real_auto_scaling_groups():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    launch_template = ec2.create_launch_template(
        LaunchTemplateName="my-lt", LaunchTemplateData={"ImageId": "ami-12345678", "InstanceType": "t2.micro"}
    )["LaunchTemplate"]["LaunchTemplateName"]
    autoscaling = boto3.client("autoscaling", region_name="us-east-1")
    autoscaling.create_auto_scaling_group(
        AutoScalingGroupName="my-asg",
        LaunchTemplate={"LaunchTemplateName": launch_template},
        MinSize=1,
        MaxSize=2,
        AvailabilityZones=["us-east-1a"],
    )

    client = AwsCloudProviderClient(FAKE_CREDENTIALS, "us-east-1")
    groups = client.list_scaling_groups("us-east-1")

    assert len(groups) == 1
    assert groups[0]["name"] == "my-asg"
    assert groups[0]["type"] == "auto_scaling_group"


@mock_aws
def test_list_subnets_returns_real_subnets():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]["VpcId"]
    ec2.create_subnet(VpcId=vpc, CidrBlock="10.0.0.0/24", AvailabilityZone="us-east-1a")

    client = AwsCloudProviderClient(FAKE_CREDENTIALS, "us-east-1")
    subnets = client.list_subnets("us-east-1")

    assert len(subnets) >= 1
    assert all(s["type"] == "subnet" for s in subnets)


@mock_aws
def test_list_security_groups_returns_real_security_groups():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    ec2.create_security_group(GroupName="my-sg", Description="test")

    client = AwsCloudProviderClient(FAKE_CREDENTIALS, "us-east-1")
    groups = client.list_security_groups("us-east-1")

    # The default security group moto seeds plus the one just created.
    assert len(groups) >= 1
    assert any(g["name"] == "my-sg" for g in groups)


@mock_aws
def test_list_alarms_returns_real_cloudwatch_alarms():
    cloudwatch = boto3.client("cloudwatch", region_name="us-east-1")
    cloudwatch.put_metric_alarm(
        AlarmName="my-alarm",
        MetricName="CPUUtilization",
        Namespace="AWS/EC2",
        Statistic="Average",
        Period=60,
        EvaluationPeriods=1,
        Threshold=80.0,
        ComparisonOperator="GreaterThanThreshold",
    )

    client = AwsCloudProviderClient(FAKE_CREDENTIALS, "us-east-1")
    alarms = client.list_alarms("us-east-1")

    assert len(alarms) == 1
    assert alarms[0]["name"] == "my-alarm"
    assert alarms[0]["type"] == "cloudwatch_alarm"
