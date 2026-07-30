"""Unit tests for Phase 27's DigitalOcean CloudProviderClient adapter -
patches the real `pydo` SDK client directly, the same pattern
test_oci_provider.py/test_alibaba_provider.py already establish (no
DigitalOcean emulator available). Every test here runs exclusively against
a mocked client - none is capable of touching a real DigitalOcean account."""
from unittest.mock import patch

import pytest
from azure.core.exceptions import HttpResponseError

from app.integrations.providers.digitalocean_provider import DigitalOceanCloudProviderClient
from app.utils.exceptions import ValidationAppError

CREDENTIALS = {"api_token": "fake-token"}
SPACES_CREDENTIALS = {
    "api_token": "fake-token",
    "spaces_access_key_id": "fake-spaces-key",
    "spaces_secret_access_key": "fake-spaces-secret",
}


def _http_error(status_code: int, message: str = "boom") -> HttpResponseError:
    error = HttpResponseError(message=message)
    error.status_code = status_code
    return error


# --- list_regions -----------------------------------------------------


@patch("app.integrations.providers.digitalocean_provider.pydo.Client")
def test_list_regions_parses_a_realistic_response(mock_client_cls):
    mock_client_cls.return_value.regions.list.return_value = {
        "regions": [
            {"slug": "nyc1", "name": "New York 1", "available": True},
            {"slug": "ams2", "name": "Amsterdam 2", "available": False},
        ]
    }
    client = DigitalOceanCloudProviderClient(CREDENTIALS, "nyc1")

    regions = client.list_regions()

    # ams2 is excluded - "available": False means new resources can't be
    # created there right now, the same READY-only filtering OCI applies.
    assert regions == [{"id": "nyc1", "display_name": "New York 1"}]


def test_list_regions_requires_credentials():
    client = DigitalOceanCloudProviderClient({}, "nyc1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "DIGITALOCEAN_CREDENTIALS_INCOMPLETE"


@patch("app.integrations.providers.digitalocean_provider.pydo.Client")
def test_list_regions_reports_credentials_rejected(mock_client_cls):
    mock_client_cls.return_value.regions.list.side_effect = _http_error(401, "invalid token")
    client = DigitalOceanCloudProviderClient(CREDENTIALS, "nyc1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "DIGITALOCEAN_REGION_CREDENTIALS_REJECTED"


@patch("app.integrations.providers.digitalocean_provider.pydo.Client")
def test_list_regions_reports_throttled_after_retries_exhausted(mock_client_cls):
    mock_client_cls.return_value.regions.list.side_effect = _http_error(429, "slow down")
    client = DigitalOceanCloudProviderClient(CREDENTIALS, "nyc1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "DIGITALOCEAN_REGION_THROTTLED"
    assert mock_client_cls.return_value.regions.list.call_count == 3


@patch("app.integrations.providers.digitalocean_provider.pydo.Client")
def test_list_regions_reports_provider_outage(mock_client_cls):
    mock_client_cls.return_value.regions.list.side_effect = _http_error(503, "down for maintenance")
    client = DigitalOceanCloudProviderClient(CREDENTIALS, "nyc1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "DIGITALOCEAN_REGION_PROVIDER_OUTAGE"


@patch("app.integrations.providers.digitalocean_provider.pydo.Client")
def test_list_regions_reports_no_regions_returned(mock_client_cls):
    mock_client_cls.return_value.regions.list.return_value = {"regions": []}
    client = DigitalOceanCloudProviderClient(CREDENTIALS, "nyc1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "DIGITALOCEAN_REGION_NO_REGIONS_RETURNED"


# --- test_connection (base class, using _identity()) -----------------------


@patch("app.integrations.providers.digitalocean_provider.pydo.Client")
def test_test_connection_succeeds(mock_client_cls):
    mock_client_cls.return_value.regions.list.return_value = {"regions": [{"slug": "nyc1", "name": "New York 1", "available": True}]}
    mock_client_cls.return_value.account.get.return_value = {
        "account": {"uuid": "fake-account-uuid", "email": "user@example.com"}
    }
    client = DigitalOceanCloudProviderClient(CREDENTIALS, "nyc1")

    result = client.test_connection()

    assert result["provider"] == "digitalocean"
    assert result["account_id"] == "fake-account-uuid"
    assert result["account_alias"] is None
    assert result["principal"] == "user@example.com"
    assert result["status"] == "success"


# --- list_resources / list_clusters / list_databases / list_networking ----


@patch("app.integrations.providers.digitalocean_provider.pydo.Client")
def test_list_resources_parses_droplets_in_the_requested_region(mock_client_cls):
    mock_client_cls.return_value.droplets.list.return_value = {
        "droplets": [
            {
                "id": 123,
                "name": "my-droplet",
                "size_slug": "s-1vcpu-1gb",
                "status": "active",
                "created_at": "2026-01-01T00:00:00Z",
                "region": {"slug": "nyc1"},
            },
            {
                "id": 456,
                "name": "other-region-droplet",
                "size_slug": "s-1vcpu-1gb",
                "status": "active",
                "region": {"slug": "ams2"},
            },
        ]
    }
    client = DigitalOceanCloudProviderClient(CREDENTIALS, "nyc1")

    resources = client.list_resources("nyc1")

    assert len(resources) == 1
    assert resources[0]["id"] == "123"
    assert resources[0]["type"] == "s-1vcpu-1gb"


@patch("app.integrations.providers.digitalocean_provider.pydo.Client")
def test_list_clusters_parses_kubernetes_clusters(mock_client_cls):
    mock_client_cls.return_value.kubernetes.list_clusters.return_value = {
        "kubernetes_clusters": [
            {"id": "cluster-1", "name": "my-cluster", "region": "nyc1", "status": {"state": "running"}, "created_at": "2026-01-01T00:00:00Z"}
        ]
    }
    client = DigitalOceanCloudProviderClient(CREDENTIALS, "nyc1")

    clusters = client.list_clusters("nyc1")

    assert clusters == [
        {
            "id": "cluster-1",
            "name": "my-cluster",
            "type": "doks",
            "region": "nyc1",
            "status": "running",
            "created_at": "2026-01-01T00:00:00Z",
        }
    ]


@patch("app.integrations.providers.digitalocean_provider.pydo.Client")
def test_list_databases_parses_database_clusters(mock_client_cls):
    mock_client_cls.return_value.databases.list_clusters.return_value = {
        "databases": [
            {"id": "db-1", "name": "my-db", "engine": "pg", "region": "nyc1", "status": "online", "created_at": "2026-01-01T00:00:00Z"}
        ]
    }
    client = DigitalOceanCloudProviderClient(CREDENTIALS, "nyc1")

    databases = client.list_databases("nyc1")

    assert databases[0]["id"] == "db-1"
    assert databases[0]["type"] == "pg"


@patch("app.integrations.providers.digitalocean_provider.pydo.Client")
def test_list_networking_parses_vpcs(mock_client_cls):
    mock_client_cls.return_value.vpcs.list.return_value = {
        "vpcs": [{"id": "vpc-1", "name": "my-vpc", "region": "nyc1", "created_at": "2026-01-01T00:00:00Z"}]
    }
    client = DigitalOceanCloudProviderClient(CREDENTIALS, "nyc1")

    resources = client.list_networking("nyc1")

    assert resources == [
        {
            "id": "vpc-1",
            "name": "my-vpc",
            "type": "vpc",
            "region": "nyc1",
            "status": "available",
            "created_at": "2026-01-01T00:00:00Z",
        }
    ]


# --- list_storage (Spaces) -------------------------------------------------


def test_list_storage_requires_spaces_keys():
    client = DigitalOceanCloudProviderClient(CREDENTIALS, "nyc1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_storage("nyc1")
    assert exc_info.value.code == "DIGITALOCEAN_SPACES_NOT_CONFIGURED"


@patch("app.integrations.providers.digitalocean_provider.boto3.client")
def test_list_storage_parses_buckets(mock_boto_client):
    mock_boto_client.return_value.list_buckets.return_value = {
        "Buckets": [{"Name": "my-space", "CreationDate": "2026-01-01T00:00:00Z"}]
    }
    client = DigitalOceanCloudProviderClient(SPACES_CREDENTIALS, "nyc1")

    resources = client.list_storage("nyc1")

    assert resources == [
        {
            "id": "my-space",
            "name": "my-space",
            "type": "spaces_bucket",
            "region": "nyc1",
            "status": "available",
            "created_at": "2026-01-01T00:00:00Z",
        }
    ]


# --- deploy / destroy ------------------------------------------------------


@patch("app.integrations.providers.digitalocean_provider.pydo.Client")
def test_deploy_and_destroy_compute(mock_client_cls):
    mock_client_cls.return_value.droplets.create.return_value = {
        "droplet": {"id": 789, "name": "my-droplet", "status": "new", "created_at": "2026-01-01T00:00:00Z"}
    }
    client = DigitalOceanCloudProviderClient(CREDENTIALS, "nyc1")

    result = client.deploy("nyc1", "compute", {"image": "ubuntu-22-04-x64", "name": "my-droplet"})
    assert result["id"] == "789"
    assert result["type"] == "s-1vcpu-1gb"

    client.destroy("nyc1", "compute", result["id"])
    mock_client_cls.return_value.droplets.destroy.assert_called_once_with(droplet_id=789)


def test_deploy_compute_requires_image():
    client = DigitalOceanCloudProviderClient(CREDENTIALS, "nyc1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.deploy("nyc1", "compute", {})
    assert exc_info.value.code == "DIGITALOCEAN_DEPLOY_SPEC_INCOMPLETE"


@patch("app.integrations.providers.digitalocean_provider.boto3.client")
def test_deploy_and_destroy_storage(mock_boto_client):
    client = DigitalOceanCloudProviderClient(SPACES_CREDENTIALS, "nyc1")

    result = client.deploy("nyc1", "storage", {"name": "my-space"})
    assert result["id"] == "my-space"
    mock_boto_client.return_value.create_bucket.assert_called_once()

    client.destroy("nyc1", "storage", result["id"])
    mock_boto_client.return_value.delete_bucket.assert_called_once_with(Bucket="my-space")


def test_deploy_storage_requires_name():
    client = DigitalOceanCloudProviderClient(SPACES_CREDENTIALS, "nyc1")
    with pytest.raises(ValidationAppError) as exc_info:
        client.deploy("nyc1", "storage", {})
    assert exc_info.value.code == "DIGITALOCEAN_DEPLOY_SPEC_INCOMPLETE"


@patch("app.integrations.providers.digitalocean_provider.pydo.Client")
def test_deploy_and_destroy_networking(mock_client_cls):
    mock_client_cls.return_value.vpcs.create.return_value = {"vpc": {"id": "vpc-1", "name": "my-vpc", "created_at": "2026-01-01T00:00:00Z"}}
    client = DigitalOceanCloudProviderClient(CREDENTIALS, "nyc1")

    result = client.deploy("nyc1", "networking", {"name": "my-vpc"})
    assert result["id"] == "vpc-1"

    client.destroy("nyc1", "networking", result["id"])
    mock_client_cls.return_value.vpcs.delete.assert_called_once_with(vpc_id="vpc-1")


# --- list_monitoring / list_costs (Phase 28) --------------------------------


@patch("app.integrations.providers.digitalocean_provider.fetch_droplet_resource_usage")
def test_list_monitoring_delegates_to_the_droplet_metrics_fetcher(mock_fetch):
    mock_fetch.return_value = {"cpu_usage_percent": 12.5}
    client = DigitalOceanCloudProviderClient(CREDENTIALS, "nyc1")

    result = client.list_monitoring("123", lookback_minutes=15)

    mock_fetch.assert_called_once_with(CREDENTIALS, "nyc1", "123", 15)
    assert result == mock_fetch.return_value


@patch("app.integrations.providers.digitalocean_provider.fetch_do_monthly_costs")
def test_list_costs_delegates_to_the_billing_fetcher(mock_fetch):
    mock_fetch.return_value = [{"service_name": "Droplets", "cost_amount": 20.0, "currency": "USD"}]
    client = DigitalOceanCloudProviderClient(CREDENTIALS, "nyc1")

    result = client.list_costs(3)

    mock_fetch.assert_called_once_with(CREDENTIALS, 3)
    assert result == mock_fetch.return_value
