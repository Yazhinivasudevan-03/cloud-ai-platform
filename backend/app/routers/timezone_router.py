"""General (non-account-scoped) timezone endpoints (Phase 22): the full
IANA timezone list (for the frontend's searchable dropdown, as a
server-driven fallback to the browser's own Intl.supportedValuesOf) and a
standalone validate-and-preview endpoint."""
from datetime import datetime, timezone as tz
from zoneinfo import available_timezones

from fastapi import APIRouter, Depends

from app.authentication.dependencies import get_current_active_user
from app.models.user import User
from app.schemas.cloud_account_timezone import TimezoneValidationResult
from app.utils.exceptions import ValidationAppError
from app.utils.timezones import compute_utc_offset, format_local, validate_iana_timezone

router = APIRouter(prefix="/timezones", tags=["Timezones"])


@router.get(
    "",
    response_model=list[str],
    summary="List every valid IANA timezone identifier (for a searchable timezone picker)",
)
def list_timezones(_current_user: User = Depends(get_current_active_user)) -> list[str]:
    return sorted(available_timezones())


@router.post(
    "/validate",
    response_model=TimezoneValidationResult,
    summary="Validate an IANA timezone identifier and preview its current UTC offset/local time",
)
def validate_timezone(
    timezone: str, _current_user: User = Depends(get_current_active_user)
) -> TimezoneValidationResult:
    try:
        validate_iana_timezone(timezone)
    except ValidationAppError as exc:
        return TimezoneValidationResult(timezone=timezone, valid=False, error=str(exc))

    now_utc = datetime.now(tz.utc).replace(tzinfo=None)
    return TimezoneValidationResult(
        timezone=timezone,
        valid=True,
        utc_offset=compute_utc_offset(timezone, now_utc),
        current_local_time=format_local(now_utc, timezone),
    )
