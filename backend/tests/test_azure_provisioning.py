"""Unit tests for Phase 25D's Azure provisioning (deploy/destroy for
compute/storage/networking) - patches the real azure-mgmt-* SDK clients
directly, the same pattern test_azure_resource_inventory.py already
establishes (no Azure emulator available). Every test here runs
exclusively against mocked clients - none is capable of touching a real
Azure subscription."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.integrations.providers.azure_provider import AzureCloudProviderClient
from app.utils.exceptions import ValidationAppError

CREDENTIALS = {
    "tenant_id": "fake-tenant",
    "client_id": "fake-client",
    "client_secret": "fake-secret",
    "subscription_id": "fake-sub",
}

RESOURCE_GROUP_SPEC = {
    "resource_group": "my-rg",
    "subnet_id": "/subscriptions/fake-sub/resourceGroups/my-rg/providers/Microsoft.Network/virtualNetworks/vnet/subnets/default",
    "admin_username": "azureuser",
    "admin_password": "SuperSecret123!",
}

VM_ID = "/subscriptions/fake-sub/resourceGroups/my-rg/providers/Microsoft.Compute/virtualMachines/my-vm"


def _poller(result_value):
    poller = MagicMock()
    poller.result.return_value = result_value
    return poller


@patch("app.integrations.providers.azure_provider.ClientSecretCredential")
@patch("app.integrations.providers.azure_provider.ComputeManagementClient")
@patch("app.integrations.providers.azure_provider.NetworkManagementClient")
def test_deploy_compute_creates_a_nic_then_a_vm(mock_network_cls, mock_compute_cls, _mock_cred):
    mock_network_cls.return_value.network_interfaces.begin_create_or_update.return_value = _poller(
        SimpleNamespace(id="/subscriptions/fake-sub/resourceGroups/my-rg/providers/Microsoft.Network/networkInterfaces/my-vm-nic")
    )
    mock_compute_cls.return_value.virtual_machines.begin_create_or_update.return_value = _poller(
        SimpleNamespace(id=VM_ID, name="my-vm", provisioning_state="Succeeded")
    )
    client = AzureCloudProviderClient(CREDENTIALS, "eastus")

    result = client.deploy("eastus", "compute", {**RESOURCE_GROUP_SPEC, "name": "my-vm"})

    assert result["name"] == "my-vm"
    assert result["type"] == "Standard_B1s"
    mock_network_cls.return_value.network_interfaces.begin_create_or_update.assert_called_once()
    mock_compute_cls.return_value.virtual_machines.begin_create_or_update.assert_called_once()


def test_deploy_compute_requires_full_spec():
    client = AzureCloudProviderClient(CREDENTIALS, "eastus")
    with pytest.raises(ValidationAppError) as exc_info:
        client.deploy("eastus", "compute", {})
    assert exc_info.value.code == "AZURE_DEPLOY_SPEC_INCOMPLETE"


@patch("app.integrations.providers.azure_provider.ClientSecretCredential")
@patch("app.integrations.providers.azure_provider.ComputeManagementClient")
def test_destroy_compute_parses_resource_group_from_the_id(mock_compute_cls, _mock_cred):
    mock_compute_cls.return_value.virtual_machines.begin_delete.return_value = _poller(None)
    client = AzureCloudProviderClient(CREDENTIALS, "eastus")

    client.destroy("eastus", "compute", VM_ID)

    mock_compute_cls.return_value.virtual_machines.begin_delete.assert_called_once_with("my-rg", "my-vm")


@patch("app.integrations.providers.azure_provider.ClientSecretCredential")
@patch("app.integrations.providers.azure_provider.StorageManagementClient")
def test_deploy_and_destroy_storage(mock_client_cls, _mock_cred):
    account_id = "/subscriptions/fake-sub/resourceGroups/my-rg/providers/Microsoft.Storage/storageAccounts/mystorage"
    mock_client_cls.return_value.storage_accounts.begin_create.return_value = _poller(
        SimpleNamespace(id=account_id, name="mystorage", provisioning_state="Succeeded", creation_time=None)
    )
    client = AzureCloudProviderClient(CREDENTIALS, "eastus")

    result = client.deploy("eastus", "storage", {"resource_group": "my-rg", "name": "mystorage"})
    assert result["name"] == "mystorage"

    client.destroy("eastus", "storage", account_id)
    mock_client_cls.return_value.storage_accounts.delete.assert_called_once_with("my-rg", "mystorage")


def test_deploy_storage_requires_resource_group_and_name():
    client = AzureCloudProviderClient(CREDENTIALS, "eastus")
    with pytest.raises(ValidationAppError) as exc_info:
        client.deploy("eastus", "storage", {})
    assert exc_info.value.code == "AZURE_DEPLOY_SPEC_INCOMPLETE"


@patch("app.integrations.providers.azure_provider.ClientSecretCredential")
@patch("app.integrations.providers.azure_provider.NetworkManagementClient")
def test_deploy_and_destroy_networking(mock_client_cls, _mock_cred):
    vnet_id = "/subscriptions/fake-sub/resourceGroups/my-rg/providers/Microsoft.Network/virtualNetworks/my-vnet"
    mock_client_cls.return_value.virtual_networks.begin_create_or_update.return_value = _poller(
        SimpleNamespace(id=vnet_id, name="my-vnet", provisioning_state="Succeeded")
    )
    mock_client_cls.return_value.virtual_networks.begin_delete.return_value = _poller(None)
    client = AzureCloudProviderClient(CREDENTIALS, "eastus")

    result = client.deploy("eastus", "networking", {"resource_group": "my-rg", "name": "my-vnet"})
    assert result["name"] == "my-vnet"

    client.destroy("eastus", "networking", vnet_id)
    mock_client_cls.return_value.virtual_networks.begin_delete.assert_called_once_with("my-rg", "my-vnet")
