"""Business logic for per-cloud-account CPU/memory/disk/network alert
threshold overrides (Phase 20-21). Ownership-checked the same way as
CloudProviderAccountService: only the account's own owner may view or
change its thresholds.
"""
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models.cloud_account_alert_threshold import CloudAccountAlertThreshold
from app.repositories.cloud_account_alert_threshold_repository import (
    CloudAccountAlertThresholdRepository,
)
from app.repositories.cloud_provider_account_repository import CloudProviderAccountRepository
from app.schemas.cloud_account_alert_threshold import (
    CloudAccountAlertThresholdRead,
    CloudAccountAlertThresholdUpdate,
)
from app.utils.exceptions import ForbiddenError, NotFoundError, ValidationAppError

_METRICS = ("cpu", "memory", "disk", "network")
_TIERS = ("warning", "critical", "saturated")
_ALL_FIELDS = [f"{metric}_{tier}_threshold" for metric in _METRICS for tier in _TIERS]


class CloudAccountAlertThresholdService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = CloudAccountAlertThresholdRepository(db)
        self.account_repository = CloudProviderAccountRepository(db)
        self.settings = get_settings()

    def _get_owned_account_or_raise(self, account_id: int, current_user_id: int):
        account = self.account_repository.get_by_id(account_id)
        if account is None:
            raise NotFoundError(
                f"Cloud provider account {account_id} not found", code="CLOUD_ACCOUNT_NOT_FOUND"
            )
        if account.user_id != current_user_id:
            raise ForbiddenError(
                "Cannot access another user's cloud provider account", code="NOT_YOUR_CLOUD_ACCOUNT"
            )
        return account

    def get(self, account_id: int, current_user_id: int) -> CloudAccountAlertThresholdRead:
        self._get_owned_account_or_raise(account_id, current_user_id)
        threshold = self.repository.get_or_create(account_id)
        return self._to_read(threshold)

    def update(
        self, account_id: int, current_user_id: int, payload: CloudAccountAlertThresholdUpdate
    ) -> CloudAccountAlertThresholdRead:
        self._get_owned_account_or_raise(account_id, current_user_id)
        threshold = self.repository.get_or_create(account_id)
        data = payload.model_dump(exclude_unset=True)

        for field in _ALL_FIELDS:
            if field in data:
                setattr(threshold, field, data[field])

        self._validate_tier_ordering(threshold)

        self.db.commit()
        self.db.refresh(threshold)
        return self._to_read(threshold)

    def _validate_tier_ordering(self, threshold: CloudAccountAlertThreshold) -> None:
        """Warning < critical < saturated must hold for the *effective*
        (override-or-default) values, otherwise a stricter tier could
        never actually fire - e.g. a custom cpu_warning_threshold of 95
        with the default cpu_critical_threshold of 80 would mean "warning"
        never triggers before "critical" already has."""
        for metric in _METRICS:
            warning_field, critical_field, saturated_field = (f"{metric}_{tier}_threshold" for tier in _TIERS)
            warning, critical, saturated = (
                self._effective(threshold, warning_field),
                self._effective(threshold, critical_field),
                self._effective(threshold, saturated_field),
            )
            if not (warning < critical < saturated):
                raise ValidationAppError(
                    f"{warning_field}={warning}, {critical_field}={critical}, "
                    f"{saturated_field}={saturated} - each tier must be strictly "
                    "greater than the one before it",
                    code="INVALID_THRESHOLD_ORDERING",
                )

    def _effective(self, threshold: CloudAccountAlertThreshold, field: str) -> float:
        value = getattr(threshold, field)
        if value is not None:
            return value
        return getattr(self.settings, f"ALERT_{field.upper()}")

    def _to_read(self, threshold: CloudAccountAlertThreshold) -> CloudAccountAlertThresholdRead:
        fields = {field: getattr(threshold, field) for field in _ALL_FIELDS}
        effective_fields = {
            f"effective_{field}": self._effective(threshold, field) for field in _ALL_FIELDS
        }
        return CloudAccountAlertThresholdRead(
            cloud_provider_account_id=threshold.cloud_provider_account_id,
            **fields,
            **effective_fields,
        )
