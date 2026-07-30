"""Unit tests for Phase 27's IBM Cloud CloudProviderClient adapter - patches
the real `ibm_vpc`/`ibm_platform_services`/`ibm_boto3` SDK client classes
directly, the same pattern test_oci_provider.py/test_alibaba_provider.py
already establish (no IBM Cloud emulator available). Every test here runs
exclusively against mocked clients - none is capable of touching a real
IBM Cloud account."""
from unittest.mock import MagicMock, patch

import pytest
from ibm_cloud_sdk_core.api_exception import ApiException

from app.integrations.providers.ibm_provider import IbmCloudProviderClient
from app.utils.exceptions import ValidationAppError

CREDENTIALS = {"api_key": "fake-api-key"}
COS_CREDENTIALS = {"api_key": "fake-api-key", "cos_instance_crn": "crn:v1:bluemix:public:cloud-object-storage:global:a/fake::"}


def _detailed_response(result: dict) -> MagicMock:
    response = MagicMock()
    response.get_result.return_value = result
    return response


# --- list_regions -----------------------------------------------------


@patch("app.integrations.providers.ibm_provider.ibm_vpc.VpcV1")
def test_list_regions_parses_a_realistic_response(mock_client_cls):
    mock_client_cls.return_value.list_regions.return_value = _detailed_response(
        {"regions": [{"name": "us-south", "status": "available"}, {"name": "eu-de", "status": "available"}]}
    )
    client = IbmCloudProviderClient(CREDENTIALS, "us-south")

    regions = client.list_regions()

    assert regions == [
        {"id": "us-south", "display_name": "US South (Dallas)"},
        {"id": "eu-de", "display_name": "Germany (Frankfurt)"},
    ]


def test_list_regions_requires_credentials():
    client = IbmCloudProviderClient({}, "us-south")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "IBM_CREDENTIALS_INCOMPLETE"


@patch("app.integrations.providers.ibm_provider.ibm_vpc.VpcV1")
def test_list_regions_reports_credentials_rejected(mock_client_cls):
    mock_client_cls.return_value.list_regions.side_effect = ApiException(401, message="invalid api key")
    client = IbmCloudProviderClient(CREDENTIALS, "us-south")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "IBM_REGION_CREDENTIALS_REJECTED"


@patch("app.integrations.providers.ibm_provider.ibm_vpc.VpcV1")
def test_list_regions_reports_credentials_rejected_for_a_400_too(mock_client_cls):
    # IBM's real IAM token endpoint rejects an unknown/invalid API key with
    # a plain 400, not 401 - confirmed via live verification against the
    # real IBM Cloud API (see docs/PHASE_27.md), so this is deliberately
    # tested as its own scenario, not assumed.
    mock_client_cls.return_value.list_regions.side_effect = ApiException(
        400, message="Provided API key could not be found."
    )
    client = IbmCloudProviderClient(CREDENTIALS, "us-south")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "IBM_REGION_CREDENTIALS_REJECTED"


@patch("app.integrations.providers.ibm_provider.ibm_vpc.VpcV1")
def test_list_regions_reports_access_denied(mock_client_cls):
    mock_client_cls.return_value.list_regions.side_effect = ApiException(403, message="not authorized")
    client = IbmCloudProviderClient(CREDENTIALS, "us-south")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "IBM_REGION_ACCESS_DENIED"


@patch("app.integrations.providers.ibm_provider.ibm_vpc.VpcV1")
def test_list_regions_reports_throttled_after_retries_exhausted(mock_client_cls):
    mock_client_cls.return_value.list_regions.side_effect = ApiException(429, message="slow down")
    client = IbmCloudProviderClient(CREDENTIALS, "us-south")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "IBM_REGION_THROTTLED"
    assert mock_client_cls.return_value.list_regions.call_count == 3


@patch("app.integrations.providers.ibm_provider.ibm_vpc.VpcV1")
def test_list_regions_reports_provider_outage(mock_client_cls):
    mock_client_cls.return_value.list_regions.side_effect = ApiException(500, message="internal error")
    client = IbmCloudProviderClient(CREDENTIALS, "us-south")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "IBM_REGION_PROVIDER_OUTAGE"


@patch("app.integrations.providers.ibm_provider.ibm_vpc.VpcV1")
def test_list_regions_reports_no_regions_returned(mock_client_cls):
    mock_client_cls.return_value.list_regions.return_value = _detailed_response({"regions": []})
    client = IbmCloudProviderClient(CREDENTIALS, "us-south")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_regions()
    assert exc_info.value.code == "IBM_REGION_NO_REGIONS_RETURNED"


# --- test_connection (base class, using _identity()) -----------------------


@patch("app.integrations.providers.ibm_provider.ibm_platform_services.IamIdentityV1")
@patch("app.integrations.providers.ibm_provider.ibm_vpc.VpcV1")
def test_test_connection_succeeds(mock_vpc_cls, mock_iam_cls):
    mock_vpc_cls.return_value.list_regions.return_value = _detailed_response(
        {"regions": [{"name": "us-south", "status": "available"}]}
    )
    mock_iam_cls.return_value.get_api_keys_details.return_value = _detailed_response(
        {"account_id": "fake-account-id", "name": "my-api-key"}
    )
    client = IbmCloudProviderClient(CREDENTIALS, "us-south")

    result = client.test_connection()

    assert result["provider"] == "ibm"
    assert result["account_id"] == "fake-account-id"
    assert result["account_alias"] is None
    assert result["principal"] == "my-api-key"
    assert result["status"] == "success"


# --- list_resources / list_networking ---------------------------------


@patch("app.integrations.providers.ibm_provider.ibm_vpc.VpcV1")
def test_list_resources_parses_instances(mock_client_cls):
    mock_client_cls.return_value.list_instances.return_value = _detailed_response(
        {
            "instances": [
                {
                    "id": "instance-1",
                    "name": "my-instance",
                    "profile": {"name": "bx2-2x8"},
                    "status": "running",
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ]
        }
    )
    client = IbmCloudProviderClient(CREDENTIALS, "us-south")

    resources = client.list_resources("us-south")

    assert resources == [
        {
            "id": "instance-1",
            "name": "my-instance",
            "type": "bx2-2x8",
            "region": "us-south",
            "status": "running",
            "created_at": "2026-01-01T00:00:00Z",
        }
    ]


@patch("app.integrations.providers.ibm_provider.ibm_vpc.VpcV1")
def test_list_networking_parses_vpcs(mock_client_cls):
    mock_client_cls.return_value.list_vpcs.return_value = _detailed_response(
        {"vpcs": [{"id": "vpc-1", "name": "my-vpc", "status": "available", "created_at": "2026-01-01T00:00:00Z"}]}
    )
    client = IbmCloudProviderClient(CREDENTIALS, "us-south")

    resources = client.list_networking("us-south")

    assert resources[0]["id"] == "vpc-1"
    assert resources[0]["type"] == "vpc"


# --- list_clusters / list_databases (Resource Controller CRN filtering) ----


@patch("app.integrations.providers.ibm_provider.ibm_platform_services.ResourceControllerV2")
def test_list_clusters_filters_by_crn_service_name(mock_client_cls):
    mock_client_cls.return_value.list_resource_instances.return_value = _detailed_response(
        {
            "resources": [
                {
                    "id": "cluster-1",
                    "name": "my-cluster",
                    "crn": "crn:v1:bluemix:public:containers-kubernetes:us-south:a/fake:cluster-1::",
                    "region_id": "us-south",
                    "state": "normal",
                    "created_at": "2026-01-01T00:00:00Z",
                },
                {
                    "id": "db-1",
                    "name": "my-db",
                    "crn": "crn:v1:bluemix:public:databases-for-postgresql:us-south:a/fake:db-1::",
                    "region_id": "us-south",
                    "state": "active",
                },
            ]
        }
    )
    client = IbmCloudProviderClient(CREDENTIALS, "us-south")

    clusters = client.list_clusters("us-south")

    assert len(clusters) == 1
    assert clusters[0]["id"] == "cluster-1"
    assert clusters[0]["type"] == "containers-kubernetes"


@patch("app.integrations.providers.ibm_provider.ibm_platform_services.ResourceControllerV2")
def test_list_databases_filters_by_crn_service_name_prefix(mock_client_cls):
    mock_client_cls.return_value.list_resource_instances.return_value = _detailed_response(
        {
            "resources": [
                {
                    "id": "db-1",
                    "name": "my-db",
                    "crn": "crn:v1:bluemix:public:databases-for-postgresql:us-south:a/fake:db-1::",
                    "region_id": "us-south",
                    "state": "active",
                    "created_at": "2026-01-01T00:00:00Z",
                },
                {
                    "id": "cluster-1",
                    "name": "my-cluster",
                    "crn": "crn:v1:bluemix:public:containers-kubernetes:us-south:a/fake:cluster-1::",
                    "region_id": "us-south",
                    "state": "normal",
                },
            ]
        }
    )
    client = IbmCloudProviderClient(CREDENTIALS, "us-south")

    databases = client.list_databases("us-south")

    assert len(databases) == 1
    assert databases[0]["id"] == "db-1"
    assert databases[0]["type"] == "databases-for-postgresql"


# --- list_storage --------------------------------------------------------


def test_list_storage_requires_cos_instance_crn():
    client = IbmCloudProviderClient(CREDENTIALS, "us-south")
    with pytest.raises(ValidationAppError) as exc_info:
        client.list_storage("us-south")
    assert exc_info.value.code == "IBM_COS_INSTANCE_NOT_CONFIGURED"


@patch("app.integrations.providers.ibm_provider.ibm_boto3.client")
def test_list_storage_parses_buckets(mock_boto_client):
    mock_boto_client.return_value.list_buckets.return_value = {
        "Buckets": [{"Name": "my-bucket", "CreationDate": "2026-01-01T00:00:00Z"}]
    }
    client = IbmCloudProviderClient(COS_CREDENTIALS, "us-south")

    resources = client.list_storage("us-south")

    assert resources == [
        {
            "id": "my-bucket",
            "name": "my-bucket",
            "type": "cos_bucket",
            "region": "us-south",
            "status": "available",
            "created_at": "2026-01-01T00:00:00Z",
        }
    ]


# --- deploy / destroy ------------------------------------------------------


@patch("app.integrations.providers.ibm_provider.ibm_vpc.VpcV1")
def test_deploy_and_destroy_compute(mock_client_cls):
    mock_client_cls.return_value.create_instance.return_value = _detailed_response(
        {"id": "instance-1", "name": "my-instance", "status": "starting", "created_at": "2026-01-01T00:00:00Z"}
    )
    client = IbmCloudProviderClient(CREDENTIALS, "us-south")
    spec = {"image_id": "image-1", "zone": "us-south-1", "subnet_id": "subnet-1", "vpc_id": "vpc-1", "name": "my-instance"}

    result = client.deploy("us-south", "compute", spec)
    assert result["id"] == "instance-1"
    assert result["type"] == "bx2-2x8"

    client.destroy("us-south", "compute", result["id"])
    mock_client_cls.return_value.delete_instance.assert_called_once_with(id="instance-1")


def test_deploy_compute_requires_full_spec():
    client = IbmCloudProviderClient(CREDENTIALS, "us-south")
    with pytest.raises(ValidationAppError) as exc_info:
        client.deploy("us-south", "compute", {})
    assert exc_info.value.code == "IBM_DEPLOY_SPEC_INCOMPLETE"


@patch("app.integrations.providers.ibm_provider.ibm_boto3.client")
def test_deploy_and_destroy_storage(mock_boto_client):
    client = IbmCloudProviderClient(COS_CREDENTIALS, "us-south")

    result = client.deploy("us-south", "storage", {"name": "my-bucket"})
    assert result["id"] == "my-bucket"
    mock_boto_client.return_value.create_bucket.assert_called_once()

    client.destroy("us-south", "storage", result["id"])
    mock_boto_client.return_value.delete_bucket.assert_called_once_with(Bucket="my-bucket")


def test_deploy_storage_requires_name():
    client = IbmCloudProviderClient(COS_CREDENTIALS, "us-south")
    with pytest.raises(ValidationAppError) as exc_info:
        client.deploy("us-south", "storage", {})
    assert exc_info.value.code == "IBM_DEPLOY_SPEC_INCOMPLETE"


@patch("app.integrations.providers.ibm_provider.ibm_vpc.VpcV1")
def test_deploy_and_destroy_networking(mock_client_cls):
    mock_client_cls.return_value.create_vpc.return_value = _detailed_response(
        {"id": "vpc-1", "name": "my-vpc", "status": "available"}
    )
    client = IbmCloudProviderClient(CREDENTIALS, "us-south")

    result = client.deploy("us-south", "networking", {"name": "my-vpc"})
    assert result["id"] == "vpc-1"

    client.destroy("us-south", "networking", result["id"])
    mock_client_cls.return_value.delete_vpc.assert_called_once_with(id="vpc-1")
