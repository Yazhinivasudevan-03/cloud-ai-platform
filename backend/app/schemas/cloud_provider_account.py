"""Pydantic schemas for the CloudProviderAccount resource.

`credentials` is intentionally a generic `dict[str, str]` rather than
provider-specific fields (e.g. AWS access_key_id/secret_access_key) - the
requirement is that a user can configure an account for *any* cloud
provider, including ones this platform has no dedicated field mapping for,
so the credential shape is left to whatever key/value pairs that provider
actually needs (an AWS account might send access_key_id/secret_access_key;
a GCP account might send a single service_account_json key; and so on).
Credentials are write-only: CloudProviderAccountRead never includes them at
all, so a client can never retrieve a previously stored secret through this
API, only overwrite it. There is no `has_credentials` flag either, since
every account requires credentials to be created in the first place - the
field would always read `true` and carry no information.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.resource_usage import ResourceUsageRead


class CloudProviderAccountBase(BaseModel):
    provider: str = Field(
        ..., min_length=2, max_length=30, description="e.g. aws, azure, gcp, or any other provider name"
    )
    account_name: str = Field(..., min_length=1, max_length=100, description="User-chosen label, unique per user")
    region: str = Field(..., min_length=1, max_length=50, description="Cloud region this account is scoped to")
    account_identifier: str | None = Field(
        default=None, max_length=100, description="e.g. AWS Account ID, Azure Subscription ID, GCP Project ID"
    )


class CloudProviderAccountCreate(CloudProviderAccountBase):
    # Overrides the base class's required `region` - Phase 25E's "All
    # Regions is the default enterprise mode": a caller that doesn't name a
    # specific region gets "all" (the aggregate sentinel - see
    # ALL_REGIONS_SENTINEL) rather than being forced to pick one up front.
    # A caller that does supply one (as this platform's own "Connect Cloud
    # Account" UI always does, for its region+timezone auto-association
    # flow) keeps that exact value, unchanged from before this phase.
    region: str | None = Field(default=None, min_length=1, max_length=50)
    credentials: dict[str, str] = Field(
        ..., min_length=1, description="Provider-specific credential key/value pairs, encrypted at rest"
    )


class CloudProviderAccountUpdate(BaseModel):
    provider: str | None = Field(default=None, min_length=2, max_length=30)
    account_name: str | None = Field(default=None, min_length=1, max_length=100)
    region: str | None = Field(default=None, min_length=1, max_length=50)
    account_identifier: str | None = Field(default=None, max_length=100)
    credentials: dict[str, str] | None = Field(
        default=None, description="If provided, replaces the stored credentials entirely"
    )
    is_active: bool | None = None


class CloudProviderAccountRead(CloudProviderAccountBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    # Phase 26: whether the stored credentials have actually been proven to
    # work via a real test_connection() call - drives the frontend's
    # "Cloud credentials are required before monitoring can begin" /
    # "No cloud credentials configured" gating states.
    credentials_validated: bool
    credentials_validated_at: datetime | None = None


class TestConnectionRequest(BaseModel):
    """Stateless pre-save validation - never persists anything, purely a
    real, live provider API call proving the given credentials work."""

    provider: str = Field(..., min_length=2, max_length=30)
    region: str = Field(..., min_length=1, max_length=50)
    credentials: dict[str, str] = Field(..., min_length=1)


class ConnectionTestResultRead(BaseModel):
    provider: str
    account_id: str | None = None
    account_alias: str | None = None
    principal: str | None = None
    region: str
    status: str


class CloudAccountDeploymentSummary(BaseModel):
    """One deployment linked to a cloud provider account, paired with its
    most recent synced resource usage snapshot (see
    CloudProviderAccountService.list_linked_deployments) - powers the "at a
    glance" usage view on the Cloud Accounts page, so a user can see live
    CPU/memory/network for every deployment tied to an account without
    opening each deployment individually."""

    deployment_id: int
    deployment_name: str
    namespace: str
    # Genuinely optional - DeploymentCreate.cloud_resource_identifier is
    # `str | None` (a deployment can exist before it's linked to a synced
    # cloud resource), so this was previously declared as a required `str`
    # and crashed this endpoint with a 500 for any such deployment.
    cloud_resource_identifier: str | None = None
    latest_usage: ResourceUsageRead | None = Field(
        default=None,
        description="Most recent resource usage snapshot for this deployment, or null if it has never been synced/recorded yet",
    )
