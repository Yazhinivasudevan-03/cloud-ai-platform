"""Optimization recommendation endpoints: read recommendations, action them
(apply/dismiss), and manually trigger the rule engine (which also runs
automatically on a schedule - see app/optimization/scheduler.py).
"""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.authentication.dependencies import get_current_active_user, require_roles
from app.controllers.optimization_controller import OptimizationController
from app.database.session import get_db
from app.models.user import User
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.optimization_recommendation import (
    OptimizationEvaluationSummary,
    OptimizationRecommendationRead,
    OptimizationRecommendationUpdate,
)

router = APIRouter(tags=["Optimization"])


@router.post(
    "/optimization/evaluate",
    response_model=OptimizationEvaluationSummary,
    summary="Manually trigger the resource optimization rule engine now (operator/admin)",
    dependencies=[Depends(require_roles("operator", "admin"))],
)
def evaluate_optimizations(db: Session = Depends(get_db)) -> OptimizationEvaluationSummary:
    return OptimizationController(db).evaluate()


@router.get(
    "/optimization-recommendations",
    response_model=PaginatedResponse[OptimizationRecommendationRead],
    summary="List optimization recommendations across all deployments (paginated, filterable) - for platform-wide dashboards",
    responses={404: {"model": ErrorResponse, "description": "Deployment not found (if filtered by deployment_id)"}},
)
def list_recommendations_global(
    deployment_id: int | None = Query(default=None),
    status: Literal["pending", "applied", "dismissed"] | None = Query(default=None),
    recommendation_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> PaginatedResponse[OptimizationRecommendationRead]:
    return OptimizationController(db).list_global(
        deployment_id, status, recommendation_type, page, page_size
    )


@router.get(
    "/deployments/{deployment_id}/optimization-recommendations",
    response_model=PaginatedResponse[OptimizationRecommendationRead],
    summary="List optimization recommendations for a deployment (paginated, filterable)",
    responses={404: {"model": ErrorResponse, "description": "Deployment not found"}},
)
def list_recommendations(
    deployment_id: int,
    status: Literal["pending", "applied", "dismissed"] | None = Query(default=None),
    recommendation_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> PaginatedResponse[OptimizationRecommendationRead]:
    return OptimizationController(db).list_for_deployment(
        deployment_id, status, recommendation_type, page, page_size
    )


@router.get(
    "/optimization-recommendations/{recommendation_id}",
    response_model=OptimizationRecommendationRead,
    summary="Get an optimization recommendation by ID",
    responses={404: {"model": ErrorResponse, "description": "Recommendation not found"}},
)
def get_recommendation(
    recommendation_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> OptimizationRecommendationRead:
    return OptimizationController(db).get(recommendation_id)


@router.patch(
    "/optimization-recommendations/{recommendation_id}",
    response_model=OptimizationRecommendationRead,
    summary="Apply or dismiss a pending optimization recommendation (operator/admin)",
    dependencies=[Depends(require_roles("operator", "admin"))],
    responses={
        404: {"model": ErrorResponse, "description": "Recommendation not found"},
        409: {"model": ErrorResponse, "description": "Recommendation is not pending"},
    },
)
def update_recommendation(
    recommendation_id: int, payload: OptimizationRecommendationUpdate, db: Session = Depends(get_db)
) -> OptimizationRecommendationRead:
    return OptimizationController(db).update_status(recommendation_id, payload.status)
