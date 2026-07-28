"""Controller layer for Alert endpoints."""
import math

from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.alert import AlertEvaluationSummary, AlertRead, AlertStatus
from app.schemas.common import PaginatedResponse, PaginationMeta
from app.services.alert_evaluation_service import AlertEvaluationService
from app.services.alert_service import AlertService


class AlertController:
    def __init__(self, db: Session):
        self.service = AlertService(db)
        self.evaluation_service = AlertEvaluationService(db)

    def get(self, alert_id: int, current_user: User) -> AlertRead:
        return AlertRead.model_validate(self.service.get(alert_id, current_user))

    def list_for_deployment(
        self,
        deployment_id: int,
        status: str | None,
        severity: str | None,
        page: int,
        page_size: int,
        current_user: User,
    ) -> PaginatedResponse[AlertRead]:
        items, total = self.service.list_for_deployment(
            deployment_id, status, severity, page, page_size, current_user
        )
        total_pages = math.ceil(total / page_size) if page_size else 0
        return PaginatedResponse[AlertRead](
            items=[AlertRead.model_validate(i) for i in items],
            meta=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=total_pages
            ),
        )

    def list_global(
        self,
        deployment_id: int | None,
        status: str | None,
        severity: str | None,
        page: int,
        page_size: int,
        current_user: User,
    ) -> PaginatedResponse[AlertRead]:
        items, total = self.service.list_global(
            deployment_id, status, severity, page, page_size, current_user
        )
        total_pages = math.ceil(total / page_size) if page_size else 0
        return PaginatedResponse[AlertRead](
            items=[AlertRead.model_validate(i) for i in items],
            meta=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=total_pages
            ),
        )

    def update_status(self, alert_id: int, new_status: AlertStatus, current_user: User) -> AlertRead:
        return AlertRead.model_validate(self.service.update_status(alert_id, new_status, current_user))

    def evaluate(self) -> AlertEvaluationSummary:
        summary = self.evaluation_service.evaluate_all()
        return AlertEvaluationSummary(**summary)
