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
