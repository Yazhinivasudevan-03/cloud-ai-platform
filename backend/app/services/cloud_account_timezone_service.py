"""Business logic for per-cloud-account multi-timezone support (Phase 22).
Ownership-checked the same way as CloudAccountAlertThresholdService: only
the account's own owner may view or change its timezone entries.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.cloud_account_timezone import CloudAccountTimezone
from app.repositories.cloud_account_timezone_repository import CloudAccountTimezoneRepository
from app.repositories.cloud_provider_account_repository import CloudProviderAccountRepository
from app.schemas.cloud_account_timezone import (
    CloudAccountTimezoneCreate,
    CloudAccountTimezoneRead,
    CloudAccountTimezoneUpdate,
)
from app.utils.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.utils.timezones import compute_utc_offset, format_local, validate_iana_timezone


class CloudAccountTimezoneService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = CloudAccountTimezoneRepository(db)
        self.account_repository = CloudProviderAccountRepository(db)

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

    def _get_owned_timezone_or_raise(
        self, account_id: int, timezone_id: int, current_user_id: int
    ) -> CloudAccountTimezone:
        self._get_owned_account_or_raise(account_id, current_user_id)
        entry = self.repository.get_by_id(timezone_id)
        if entry is None or entry.cloud_provider_account_id != account_id:
            raise NotFoundError(
                f"Timezone entry {timezone_id} not found for this account",
                code="CLOUD_ACCOUNT_TIMEZONE_NOT_FOUND",
            )
        return entry

    def list_for_account(self, account_id: int, current_user_id: int) -> list[CloudAccountTimezoneRead]:
        account = self._get_owned_account_or_raise(account_id, current_user_id)
        entries = self.repository.list_for_account(account_id)
        return [self._to_read(entry, account.provider) for entry in entries]

    def create(
        self, account_id: int, current_user_id: int, payload: CloudAccountTimezoneCreate
    ) -> CloudAccountTimezoneRead:
        account = self._get_owned_account_or_raise(account_id, current_user_id)
        validate_iana_timezone(payload.timezone)

        existing = [
            e for e in self.repository.list_for_account(account_id)
            if e.region == payload.region and e.timezone == payload.timezone
        ]
        if existing:
            raise ConflictError(
                f"This account already has a '{payload.region}' / '{payload.timezone}' entry",
                code="CLOUD_ACCOUNT_TIMEZONE_EXISTS",
            )

        entry = CloudAccountTimezone(
            cloud_provider_account_id=account_id,
            region=payload.region,
            availability_zone=payload.availability_zone,
            label=payload.label,
            timezone=payload.timezone,
        )
        entry = self.repository.create(entry)
        return self._to_read(entry, account.provider)

    def update(
        self, account_id: int, timezone_id: int, current_user_id: int, payload: CloudAccountTimezoneUpdate
    ) -> CloudAccountTimezoneRead:
        entry = self._get_owned_timezone_or_raise(account_id, timezone_id, current_user_id)
        data = payload.model_dump(exclude_unset=True)

        if "timezone" in data and data["timezone"] is not None:
            validate_iana_timezone(data["timezone"])

        for field in ("region", "availability_zone", "label", "timezone"):
            if field in data:
                setattr(entry, field, data[field])

        self.db.commit()
        self.db.refresh(entry)
        return self._to_read(entry, entry.cloud_provider_account.provider)

    def delete(self, account_id: int, timezone_id: int, current_user_id: int) -> None:
        entry = self._get_owned_timezone_or_raise(account_id, timezone_id, current_user_id)
        self.repository.delete(entry)

    def _to_read(self, entry: CloudAccountTimezone, provider: str) -> CloudAccountTimezoneRead:
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        return CloudAccountTimezoneRead(
            id=entry.id,
            cloud_provider_account_id=entry.cloud_provider_account_id,
            provider=provider,
            region=entry.region,
            availability_zone=entry.availability_zone,
            label=entry.label,
            timezone=entry.timezone,
            utc_offset=compute_utc_offset(entry.timezone, now_utc),
            current_local_time=format_local(now_utc, entry.timezone),
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )
