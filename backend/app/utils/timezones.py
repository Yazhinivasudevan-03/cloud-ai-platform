"""IANA timezone validation and conversion (Phase 22) - built entirely on
Python's stdlib `zoneinfo` (its own bundled IANA tzdata), never manual
offset arithmetic. This is the only correct way to handle Daylight Saving
Time: the UTC offset for a given IANA zone (e.g. "Europe/London") depends
on which specific date/time you're asking about (GMT in January, BST in
July), not the zone name alone - a static stored offset would silently go
stale across a DST transition, so nothing in this module or its callers
ever stores one.

Every timestamp elsewhere in this project is naive-UTC (no tzinfo
attached - see docs/PHASE_12/13 conventions), so `to_local`/`format_local`
below take a naive-UTC `datetime` and attach `timezone.utc` explicitly
before converting, rather than assuming the caller already did so.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.utils.exceptions import ValidationAppError


def validate_iana_timezone(tz_name: str) -> None:
    """Raises ValidationAppError if `tz_name` is not a real IANA timezone
    identifier. Used by the CloudAccountTimezone create/update API so a
    typo (or a fixed-offset string like "+05:30") is rejected up front
    rather than silently failing later when something tries to use it."""
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationAppError(
            f"'{tz_name}' is not a valid IANA timezone identifier (e.g. "
            "'Europe/London', 'Asia/Kolkata', 'America/New_York')",
            code="INVALID_TIMEZONE",
        ) from exc


def to_local(utc_naive: datetime, tz_name: str) -> datetime:
    """Converts a naive-UTC datetime into an aware datetime in `tz_name`,
    with the correct DST-adjusted offset for that exact instant."""
    return utc_naive.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz_name))


def compute_utc_offset(tz_name: str, at: datetime | None = None) -> str:
    """The UTC offset (e.g. "+01:00", "+05:30", "-05:00") that `tz_name`
    has at `at` (a naive-UTC datetime; defaults to right now) - computed
    fresh every call via zoneinfo, never a stored/cached value, so it's
    always correct across a DST transition."""
    reference = at if at is not None else datetime.now(timezone.utc).replace(tzinfo=None)
    local = to_local(reference, tz_name)
    offset = local.utcoffset()
    total_minutes = int(offset.total_seconds() // 60) if offset else 0
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"{sign}{hours:02d}:{minutes:02d}"


def format_local(utc_naive: datetime, tz_name: str) -> str:
    """Human-readable local time including the abbreviation actually in
    effect for that instant (e.g. "2026-08-15 18:35 BST", "2026-01-15
    14:20 GMT") - the tzname() abbreviation, like the offset, is resolved
    fresh per-instant by zoneinfo, not assumed from the zone name alone."""
    local = to_local(utc_naive, tz_name)
    tz_abbreviation = local.tzname() or tz_name
    return f"{local.strftime('%Y-%m-%d %H:%M')} {tz_abbreviation}"
