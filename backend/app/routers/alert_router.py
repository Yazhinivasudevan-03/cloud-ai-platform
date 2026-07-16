"""Alert endpoints: read alerts, acknowledge/resolve them, and manually
trigger the rule engine (which also runs automatically on a schedule - see
app/alerts/scheduler.py).
"""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.authentication.dependencies import get_current_active_user, require_roles
from app.controllers.alert_controller import AlertController
from app.database.session import get_db
from app.models.user import User
from app.schemas.alert import AlertEvaluationSummary, AlertRead, AlertUpdate
from app.schemas.common import ErrorResponse, PaginatedResponse

router = APIRouter(tags=["Alerts"])


@router.post(
    "/alerts/evaluate",
    response_model=AlertEvaluationSummary,
    summary="Manually trigger the alert rule engine now (operator/admin)",
    dependencies=[Depends(require_roles("operator", "admin"))],
)
def evaluate_alerts(db: Session = Depends(get_db)) -> AlertEvaluationSummary:
    return AlertController(db).evaluate()


@router.get(
    "/alerts",
    response_model=PaginatedResponse[AlertRead],
    summary="List alerts across all deployments (paginated, filterable) - for platform-wide dashboards",
    responses={404: {"model": ErrorResponse, "description": "Deployment not found (if filtered by deployment_id)"}},
)
def list_alerts_global(
    deployment_id: int | None = Query(default=None),
    status: Literal["active", "acknowledged", "resolved"] | None = Query(default=None),
    severity: Literal["warning", "critical"] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> PaginatedResponse[AlertRead]:
    return AlertController(db).list_global(deployment_id, status, severity, page, page_size)


@router.get(
    "/deployments/{deployment_id}/alerts",
    response_model=PaginatedResponse[AlertRead],
    summary="List alerts for a deployment (paginated, filterable)",
    responses={404: {"model": ErrorResponse, "description": "Deployment not found"}},
)
def list_alerts(
    deployment_id: int,
    status: Literal["active", "acknowledged", "resolved"] | None = Query(default=None),
    severity: Literal["warning", "critical"] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> PaginatedResponse[AlertRead]:
    return AlertController(db).list_for_deployment(deployment_id, status, severity, page, page_size)


@router.get(
    "/alerts/{alert_id}",
    response_model=AlertRead,
    summary="Get an alert by ID",
    responses={404: {"model": ErrorResponse, "description": "Alert not found"}},
)
def get_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> AlertRead:
    return AlertController(db).get(alert_id)


@router.patch(
    "/alerts/{alert_id}",
    response_model=AlertRead,
    summary="Acknowledge or resolve an alert (operator/admin)",
    dependencies=[Depends(require_roles("operator", "admin"))],
    responses={
        404: {"model": ErrorResponse, "description": "Alert not found"},
        409: {"model": ErrorResponse, "description": "Invalid status transition"},
    },
)
def update_alert(alert_id: int, payload: AlertUpdate, db: Session = Depends(get_db)) -> AlertRead:
    return AlertController(db).update_status(alert_id, payload.status)
