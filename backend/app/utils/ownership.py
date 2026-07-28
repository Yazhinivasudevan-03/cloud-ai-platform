"""Ownership-checking helpers for Phase 24's per-user data isolation.

The core domain (Project -> Microservice -> Deployment -> Pod/Metric/
ResourceUsage/Prediction/AnomalyDetection/FailurePrediction/
OptimizationRecommendation, plus CloudCost) was previously modeled as a
single shared organization's internal tool - every authenticated user
could see every project; role (viewer/operator/admin) only gated WHAT
actions were allowed, never WHOSE data was visible (see the old
project_router.py module docstring). Phase 24 converts this to genuine
per-tenant isolation: a project - and everything nested under it - is
visible only to that project's own owner, or a platform `is_superuser`
(the actual cross-tenant operator flag; the `admin` role itself is now
purely an app-management capability within a tenant, not a data-access
bypass).
"""
from app.models.project import Project
from app.models.user import User
from app.utils.exceptions import ForbiddenError


def can_access_project(project: Project, current_user: User) -> bool:
    return current_user.is_superuser or project.owner_id == current_user.id


def raise_if_cannot_access_project(project: Project, current_user: User) -> None:
    if not can_access_project(project, current_user):
        raise ForbiddenError("Cannot access another user's project", code="NOT_YOUR_PROJECT")
