"""Pydantic schemas for the Role resource."""
from pydantic import BaseModel, ConfigDict, Field


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None


class RoleAssignment(BaseModel):
    """Request body for granting/revoking a role on a user."""

    role_name: str = Field(..., min_length=2, max_length=50)
