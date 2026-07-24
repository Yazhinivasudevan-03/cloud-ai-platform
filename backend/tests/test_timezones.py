"""Unit tests for app/utils/timezones.py (Phase 22) - real DST behavior,
not mocked, via Python's own stdlib zoneinfo/tzdata."""
from datetime import datetime

import pytest

from app.utils.exceptions import ValidationAppError
from app.utils.timezones import compute_utc_offset, format_local, to_local, validate_iana_timezone


def test_validate_iana_timezone_accepts_real_zones():
    for tz in ("Europe/London", "Asia/Kolkata", "America/New_York", "Asia/Singapore", "Australia/Sydney"):
        validate_iana_timezone(tz)  # must not raise


def test_validate_iana_timezone_rejects_garbage():
    with pytest.raises(ValidationAppError) as exc_info:
        validate_iana_timezone("Not/A_Real_Zone")
    assert exc_info.value.code == "INVALID_TIMEZONE"


def test_validate_iana_timezone_rejects_a_raw_utc_offset():
    """A fixed-offset string like "+05:30" is exactly the kind of input
    this platform must never accept as an IANA identifier - it has no DST
    rules and isn't resolvable by zoneinfo."""
    with pytest.raises(ValidationAppError):
        validate_iana_timezone("+05:30")


def test_london_offset_is_gmt_in_january_and_bst_in_july():
    """The real point of this feature: the same IANA zone has a different
    UTC offset depending on the date, handled automatically by zoneinfo -
    never manually computed."""
    winter = datetime(2026, 1, 15, 12, 0, 0)
    summer = datetime(2026, 7, 15, 12, 0, 0)

    assert compute_utc_offset("Europe/London", winter) == "+00:00"
    assert compute_utc_offset("Europe/London", summer) == "+01:00"


def test_kolkata_offset_is_fixed_half_hour_year_round():
    winter = datetime(2026, 1, 15, 12, 0, 0)
    summer = datetime(2026, 7, 15, 12, 0, 0)

    assert compute_utc_offset("Asia/Kolkata", winter) == "+05:30"
    assert compute_utc_offset("Asia/Kolkata", summer) == "+05:30"


def test_to_local_converts_utc_to_the_correct_wall_clock_time():
    utc = datetime(2026, 8, 15, 17, 35, 0)  # BST is UTC+1 in August

    local = to_local(utc, "Europe/London")

    assert local.hour == 18
    assert local.minute == 35


def test_format_local_includes_the_correct_dst_abbreviation():
    summer_utc = datetime(2026, 8, 15, 17, 35, 0)
    winter_utc = datetime(2026, 1, 15, 17, 35, 0)

    summer_label = format_local(summer_utc, "Europe/London")
    winter_label = format_local(winter_utc, "Europe/London")

    assert "18:35 BST" in summer_label
    assert "17:35 GMT" in winter_label


def test_format_local_for_kolkata():
    utc = datetime(2026, 8, 15, 17, 35, 0)

    label = format_local(utc, "Asia/Kolkata")

    assert "23:05" in label  # +5:30
    assert "IST" in label
