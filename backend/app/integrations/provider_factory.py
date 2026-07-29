"""Factory for CloudProviderClient adapters (Phase 25) - the one place a
new cloud provider is ever registered. Every service/controller that needs
provider-specific behavior goes through get_cloud_provider_client() and
then only ever calls the returned object's interface methods; none of them
ever branches on a provider-name string themselves.

Adding a 6th provider is exactly one line in _PROVIDER_CLIENTS below plus a
new adapter class under app/integrations/providers/ - nothing else in this
codebase changes, proving the "pluggable without changing existing code"
requirement.
"""
from app.integrations.cloud_provider_client import CloudProviderClient
from app.integrations.providers.alibaba_provider import AlibabaCloudProviderClient
from app.integrations.providers.aws_provider import AwsCloudProviderClient
from app.integrations.providers.azure_provider import AzureCloudProviderClient
from app.integrations.providers.gcp_provider import GcpCloudProviderClient
from app.integrations.providers.oci_provider import OciCloudProviderClient
from app.utils.exceptions import ValidationAppError

_PROVIDER_CLIENTS: dict[str, type[CloudProviderClient]] = {
    "aws": AwsCloudProviderClient,
    "azure": AzureCloudProviderClient,
    "gcp": GcpCloudProviderClient,
    "oci": OciCloudProviderClient,
    "alibaba": AlibabaCloudProviderClient,
}


def supported_providers() -> list[str]:
    return sorted(_PROVIDER_CLIENTS)


def get_cloud_provider_client(provider: str, credentials: dict[str, str], region: str) -> CloudProviderClient:
    client_class = _PROVIDER_CLIENTS.get(provider)
    if client_class is None:
        raise ValidationAppError(
            f"Provider '{provider}' is not yet supported - only {', '.join(supported_providers())} "
            "are currently supported",
            code="CLOUD_PROVIDER_NOT_SUPPORTED",
        )
    return client_class(credentials, region)
