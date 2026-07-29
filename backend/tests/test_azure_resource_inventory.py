"""Unit tests for Phase 25C's Azure resource inventory (compute/clusters/
databases/storage/networking) - patches the real azure-mgmt-* SDK clients
directly, the same pattern test_azure_monitor.py/test_provider_region_discovery.py
already establish (no Azure emulator available)."""
from types import SimpleNamespace
from unittest.mock import patch

from app.integrations.providers.azure_provider import AzureCloudProviderClient

CREDENTIALS = {
    "tenant_id": "fake-tenant",
    "client_id": "fake-client",
    "client_secret": "fake-secret",
    "subscription_id": "fake-sub",
}


def _vm(name: str, location: str, vm_size: str = "Standard_B1s", state: str = "Succeeded") -> SimpleNamespace:
    return SimpleNamespace(
        id=f"/subscriptions/fake-sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/{name}",
        name=name,
        location=location,
        hardware_profile=SimpleNamespace(vm_size=vm_size),
        provisioning_state=state,
    )


@patch("app.integrations.providers.azure_provider.ClientSecretCredential")
@patch("app.integrations.providers.azure_provider.ComputeManagementClient")
def test_list_resources_parses_real_virtual_machines(mock_client_cls, _mock_cred):
    mock_client_cls.return_value.virtual_machines.list_all.return_value = [
        _vm("vm-eastus", "eastus"),
        _vm("vm-westus", "westus"),
    ]
    client = AzureCloudProviderClient(CREDENTIALS, "eastus")

    resources = client.list_resources("eastus")

    assert len(resources) == 1
    assert resources[0]["name"] == "vm-eastus"
    assert resources[0]["type"] == "Standard_B1s"


@patch("app.integrations.providers.azure_provider.ClientSecretCredential")
@patch("app.integrations.providers.azure_provider.ContainerServiceClient")
def test_list_clusters_parses_real_managed_clusters(mock_client_cls, _mock_cred):
    mock_client_cls.return_value.managed_clusters.list.return_value = [
        SimpleNamespace(id="cluster-id", name="my-aks", location="eastus", provisioning_state="Succeeded"),
    ]
    client = AzureCloudProviderClient(CREDENTIALS, "eastus")

    clusters = client.list_clusters("eastus")

    assert len(clusters) == 1
    assert clusters[0]["name"] == "my-aks"
    assert clusters[0]["type"] == "aks"


@patch("app.integrations.providers.azure_provider.ClientSecretCredential")
@patch("app.integrations.providers.azure_provider.SqlManagementClient")
def test_list_databases_parses_real_sql_servers(mock_client_cls, _mock_cred):
    mock_client_cls.return_value.servers.list.return_value = [
        SimpleNamespace(id="server-id", name="my-sql-server", location="eastus", state="Ready"),
    ]
    client = AzureCloudProviderClient(CREDENTIALS, "eastus")

    databases = client.list_databases("eastus")

    assert len(databases) == 1
    assert databases[0]["name"] == "my-sql-server"
    assert databases[0]["type"] == "azure_sql_server"


@patch("app.integrations.providers.azure_provider.ClientSecretCredential")
@patch("app.integrations.providers.azure_provider.StorageManagementClient")
def test_list_storage_parses_real_storage_accounts(mock_client_cls, _mock_cred):
    mock_client_cls.return_value.storage_accounts.list.return_value = [
        SimpleNamespace(
            id="sa-id",
            name="mystorageacct",
            location="eastus",
            status_of_primary="available",
            provisioning_state="Succeeded",
            creation_time=None,
        ),
    ]
    client = AzureCloudProviderClient(CREDENTIALS, "eastus")

    accounts = client.list_storage("eastus")

    assert len(accounts) == 1
    assert accounts[0]["name"] == "mystorageacct"
    assert accounts[0]["type"] == "storage_account"


@patch("app.integrations.providers.azure_provider.ClientSecretCredential")
@patch("app.integrations.providers.azure_provider.NetworkManagementClient")
def test_list_networking_parses_real_virtual_networks(mock_client_cls, _mock_cred):
    mock_client_cls.return_value.virtual_networks.list_all.return_value = [
        SimpleNamespace(id="vnet-id", name="my-vnet", location="eastus", provisioning_state="Succeeded"),
    ]
    client = AzureCloudProviderClient(CREDENTIALS, "eastus")

    vnets = client.list_networking("eastus")

    assert len(vnets) == 1
    assert vnets[0]["name"] == "my-vnet"
    assert vnets[0]["type"] == "virtual_network"
