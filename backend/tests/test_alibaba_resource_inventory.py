"""Unit tests for Phase 25C's Alibaba Cloud resource inventory (compute/
clusters/databases/storage/networking) - patches the real Tea-based SDK
client classes (+ the classic oss2 SDK for OSS) directly, the same pattern
test_alibaba_provider.py already establishes (no Alibaba Cloud emulator
available)."""
from types import SimpleNamespace
from unittest.mock import patch

from app.integrations.providers.alibaba_provider import AlibabaCloudProviderClient

CREDENTIALS = {"access_key_id": "fake-ak", "access_key_secret": "fake-sk"}


@patch("app.integrations.providers.alibaba_provider.EcsClient")
def test_list_resources_parses_real_instances(mock_client_cls):
    instance = SimpleNamespace(
        instance_id="i-fake123", instance_name="my-ecs", instance_type="ecs.t5-lc1m1.small",
        status="Running", creation_time="2026-01-01T00:00:00Z",
    )
    mock_client_cls.return_value.describe_instances.return_value = SimpleNamespace(
        body=SimpleNamespace(instances=SimpleNamespace(instance=[instance]))
    )
    client = AlibabaCloudProviderClient(CREDENTIALS, "cn-hangzhou")

    resources = client.list_resources("cn-hangzhou")

    assert len(resources) == 1
    assert resources[0]["name"] == "my-ecs"
    assert resources[0]["type"] == "ecs.t5-lc1m1.small"


@patch("app.integrations.providers.alibaba_provider.CsClient")
def test_list_clusters_parses_real_ack_clusters(mock_client_cls):
    cluster = SimpleNamespace(
        cluster_id="c-fake123", name="my-ack", state="running", cluster_type="ManagedKubernetes",
        created="2026-01-01T00:00:00Z",
    )
    mock_client_cls.return_value.describe_clusters_v1.return_value = SimpleNamespace(
        body=SimpleNamespace(clusters=[cluster])
    )
    client = AlibabaCloudProviderClient(CREDENTIALS, "cn-hangzhou")

    clusters = client.list_clusters("cn-hangzhou")

    assert len(clusters) == 1
    assert clusters[0]["name"] == "my-ack"
    assert clusters[0]["type"] == "ManagedKubernetes"


@patch("app.integrations.providers.alibaba_provider.RdsClient")
def test_list_databases_parses_real_rds_instances(mock_client_cls):
    db = SimpleNamespace(
        dbinstance_id="rm-fake123", dbinstance_description="my-rds", engine="MySQL",
        dbinstance_status="Running", create_time="2026-01-01T00:00:00Z",
    )
    mock_client_cls.return_value.describe_dbinstances.return_value = SimpleNamespace(
        body=SimpleNamespace(items=SimpleNamespace(dbinstance=[db]))
    )
    client = AlibabaCloudProviderClient(CREDENTIALS, "cn-hangzhou")

    databases = client.list_databases("cn-hangzhou")

    assert len(databases) == 1
    assert databases[0]["name"] == "my-rds"
    assert databases[0]["type"] == "MySQL"


@patch("app.integrations.providers.alibaba_provider.oss2.Service")
def test_list_storage_parses_real_oss_buckets(mock_service_cls):
    bucket = SimpleNamespace(name="my-oss-bucket", creation_date="2026-01-01T00:00:00Z")
    mock_service_cls.return_value.list_buckets.return_value = SimpleNamespace(buckets=[bucket])
    client = AlibabaCloudProviderClient(CREDENTIALS, "cn-hangzhou")

    buckets = client.list_storage("cn-hangzhou")

    assert len(buckets) == 1
    assert buckets[0]["name"] == "my-oss-bucket"
    assert buckets[0]["type"] == "oss_bucket"


@patch("app.integrations.providers.alibaba_provider.VpcClient")
def test_list_networking_parses_real_vpcs(mock_client_cls):
    vpc = SimpleNamespace(vpc_id="vpc-fake123", vpc_name="my-vpc", status="Available", creation_time="2026-01-01T00:00:00Z")
    mock_client_cls.return_value.describe_vpcs.return_value = SimpleNamespace(
        body=SimpleNamespace(vpcs=SimpleNamespace(vpc=[vpc]))
    )
    client = AlibabaCloudProviderClient(CREDENTIALS, "cn-hangzhou")

    vpcs = client.list_networking("cn-hangzhou")

    assert len(vpcs) == 1
    assert vpcs[0]["name"] == "my-vpc"
    assert vpcs[0]["type"] == "vpc"
