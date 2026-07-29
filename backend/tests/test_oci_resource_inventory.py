"""Unit tests for Phase 25C's OCI resource inventory (compute/clusters/
databases/storage/networking) - patches the real `oci` SDK client classes
directly, the same pattern test_oci_provider.py already establishes (no
OCI emulator available)."""
from types import SimpleNamespace
from unittest.mock import patch

from app.integrations.providers.oci_provider import OciCloudProviderClient

CREDENTIALS = {
    "user": "ocid1.user.oc1..fake",
    "tenancy": "ocid1.tenancy.oc1..fake",
    "fingerprint": "aa:bb:cc:dd",
    "key_content": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
}


@patch("app.integrations.providers.oci_provider.oci.core.ComputeClient")
def test_list_resources_parses_real_instances(mock_client_cls):
    instance = SimpleNamespace(
        id="ocid1.instance.oc1..fake", display_name="my-instance", shape="VM.Standard.E2.1",
        lifecycle_state="RUNNING", time_created="2026-01-01T00:00:00Z",
    )
    mock_client_cls.return_value.list_instances.return_value = SimpleNamespace(data=[instance])
    client = OciCloudProviderClient(CREDENTIALS, "us-ashburn-1")

    resources = client.list_resources("us-ashburn-1")

    assert len(resources) == 1
    assert resources[0]["name"] == "my-instance"
    assert resources[0]["type"] == "VM.Standard.E2.1"


@patch("app.integrations.providers.oci_provider.oci.container_engine.ContainerEngineClient")
def test_list_clusters_parses_real_oke_clusters(mock_client_cls):
    cluster = SimpleNamespace(
        id="ocid1.cluster.oc1..fake", name="my-oke", lifecycle_state="ACTIVE",
        metadata=SimpleNamespace(time_created="2026-01-01T00:00:00Z"),
    )
    mock_client_cls.return_value.list_clusters.return_value = SimpleNamespace(data=[cluster])
    client = OciCloudProviderClient(CREDENTIALS, "us-ashburn-1")

    clusters = client.list_clusters("us-ashburn-1")

    assert len(clusters) == 1
    assert clusters[0]["name"] == "my-oke"
    assert clusters[0]["type"] == "oke"


@patch("app.integrations.providers.oci_provider.oci.database.DatabaseClient")
def test_list_databases_parses_real_db_systems(mock_client_cls):
    db_system = SimpleNamespace(
        id="ocid1.dbsystem.oc1..fake", display_name="my-db", database_edition="STANDARD_EDITION",
        lifecycle_state="AVAILABLE", time_created="2026-01-01T00:00:00Z",
    )
    mock_client_cls.return_value.list_db_systems.return_value = SimpleNamespace(data=[db_system])
    client = OciCloudProviderClient(CREDENTIALS, "us-ashburn-1")

    databases = client.list_databases("us-ashburn-1")

    assert len(databases) == 1
    assert databases[0]["name"] == "my-db"
    assert databases[0]["type"] == "STANDARD_EDITION"


@patch("app.integrations.providers.oci_provider.oci.object_storage.ObjectStorageClient")
def test_list_storage_parses_real_buckets(mock_client_cls):
    bucket = SimpleNamespace(name="my-bucket", time_created="2026-01-01T00:00:00Z")
    mock_client_cls.return_value.get_namespace.return_value = SimpleNamespace(data="my-namespace")
    mock_client_cls.return_value.list_buckets.return_value = SimpleNamespace(data=[bucket])
    client = OciCloudProviderClient(CREDENTIALS, "us-ashburn-1")

    buckets = client.list_storage("us-ashburn-1")

    assert len(buckets) == 1
    assert buckets[0]["name"] == "my-bucket"
    assert buckets[0]["type"] == "object_storage_bucket"


@patch("app.integrations.providers.oci_provider.oci.core.VirtualNetworkClient")
def test_list_networking_parses_real_vcns(mock_client_cls):
    vcn = SimpleNamespace(
        id="ocid1.vcn.oc1..fake", display_name="my-vcn", lifecycle_state="AVAILABLE",
        time_created="2026-01-01T00:00:00Z",
    )
    mock_client_cls.return_value.list_vcns.return_value = SimpleNamespace(data=[vcn])
    client = OciCloudProviderClient(CREDENTIALS, "us-ashburn-1")

    vcns = client.list_networking("us-ashburn-1")

    assert len(vcns) == 1
    assert vcns[0]["name"] == "my-vcn"
    assert vcns[0]["type"] == "vcn"
