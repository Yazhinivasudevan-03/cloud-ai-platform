"""Unit tests for Phase 25C's GCP resource inventory (compute/clusters/
databases/storage/networking) - patches the real google-cloud-* SDK clients
directly, the same pattern test_gcp_monitoring.py/test_provider_region_discovery.py
already establish (no GCP emulator available)."""
import json
from types import SimpleNamespace
from unittest.mock import patch

FAKE_SERVICE_ACCOUNT_INFO = {"type": "service_account", "project_id": "fake-project"}
CREDENTIALS = {"service_account_json": json.dumps(FAKE_SERVICE_ACCOUNT_INFO)}

from app.integrations.providers.gcp_provider import GcpCloudProviderClient  # noqa: E402


@patch("app.integrations.providers.gcp_provider.service_account")
@patch("app.integrations.providers.gcp_provider.compute_v1.InstancesClient")
def test_list_resources_parses_real_instances(mock_client_cls, _mock_service_account):
    instance = SimpleNamespace(id=123, name="my-vm", machine_type=".../machineTypes/e2-micro", status="RUNNING")
    scoped_list = SimpleNamespace(instances=[instance])
    mock_client_cls.return_value.aggregated_list.return_value = [
        ("zones/us-central1-a", scoped_list),
        ("zones/europe-west1-b", SimpleNamespace(instances=[])),
    ]
    client = GcpCloudProviderClient(CREDENTIALS, "us-central1")

    resources = client.list_resources("us-central1")

    assert len(resources) == 1
    assert resources[0]["name"] == "my-vm"
    assert resources[0]["type"] == "e2-micro"


@patch("app.integrations.providers.gcp_provider.service_account")
@patch("app.integrations.providers.gcp_provider.container_v1.ClusterManagerClient")
def test_list_clusters_parses_real_gke_clusters(mock_client_cls, _mock_service_account):
    cluster = SimpleNamespace(name="my-gke", location="us-central1", zone="", status=SimpleNamespace(name="RUNNING"))
    mock_client_cls.return_value.list_clusters.return_value = SimpleNamespace(clusters=[cluster])
    client = GcpCloudProviderClient(CREDENTIALS, "us-central1")

    clusters = client.list_clusters("us-central1")

    assert len(clusters) == 1
    assert clusters[0]["name"] == "my-gke"
    assert clusters[0]["type"] == "gke"


@patch("app.integrations.providers.gcp_provider.build_google_api_client")
@patch("app.integrations.providers.gcp_provider.service_account")
def test_list_databases_parses_real_cloud_sql_instances(_mock_service_account, mock_build):
    mock_service = mock_build.return_value
    mock_service.instances.return_value.list.return_value.execute.return_value = {
        "items": [
            {"name": "my-sql", "region": "us-central1", "databaseVersion": "MYSQL_8_0", "state": "RUNNABLE"},
            {"name": "other-region-sql", "region": "europe-west1", "databaseVersion": "MYSQL_8_0", "state": "RUNNABLE"},
        ]
    }
    client = GcpCloudProviderClient(CREDENTIALS, "us-central1")

    databases = client.list_databases("us-central1")

    assert len(databases) == 1
    assert databases[0]["name"] == "my-sql"
    assert databases[0]["type"] == "MYSQL_8_0"


@patch("app.integrations.providers.gcp_provider.storage.Client")
@patch("app.integrations.providers.gcp_provider.service_account")
def test_list_storage_parses_real_buckets(_mock_service_account, mock_storage_client_cls):
    bucket = SimpleNamespace(name="my-bucket", location="US-CENTRAL1", time_created=None)
    mock_storage_client_cls.return_value.list_buckets.return_value = [bucket]
    client = GcpCloudProviderClient(CREDENTIALS, "us-central1")

    buckets = client.list_storage("us-central1")

    assert len(buckets) == 1
    assert buckets[0]["name"] == "my-bucket"
    assert buckets[0]["type"] == "gcs_bucket"


@patch("app.integrations.providers.gcp_provider.service_account")
@patch("app.integrations.providers.gcp_provider.compute_v1.NetworksClient")
def test_list_networking_parses_real_networks(mock_client_cls, _mock_service_account):
    network = SimpleNamespace(id=456, name="my-vpc")
    mock_client_cls.return_value.list.return_value = [network]
    client = GcpCloudProviderClient(CREDENTIALS, "us-central1")

    networks = client.list_networking("us-central1")

    assert len(networks) == 1
    assert networks[0]["name"] == "my-vpc"
    assert networks[0]["type"] == "vpc_network"
