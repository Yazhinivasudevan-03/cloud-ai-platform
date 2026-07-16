"""Shared Pydantic schemas reused across API responses: errors and pagination envelopes."""
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error code, e.g. INVALID_CREDENTIALS")
    message: str = Field(..., description="Human-readable error message")


class ErrorResponse(BaseModel):
    """Consistent error envelope returned by every failed API call."""

    error: ErrorDetail


class PaginationMeta(BaseModel):
    total: int = Field(..., description="Total number of matching records")
    page: int = Field(..., description="Current page number, 1-indexed")
    page_size: int = Field(..., description="Number of records per page")
    total_pages: int = Field(..., description="Total number of pages available")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic envelope for any paginated list endpoint."""

    items: list[T]
    meta: PaginationMeta
