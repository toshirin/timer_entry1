from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

LONDON_TZ = "Europe/London"
NEW_YORK_TZ = "America/New_York"

US_UK_DST_MISMATCH = "us_uk_dst_mismatch"
SUPPORTED_EXCLUDE_WINDOWS = (US_UK_DST_MISMATCH,)


def _is_dst_at_noon(date_text: str, tz_name: str) -> bool:
    year, month, day = [int(part) for part in date_text.split("-")]
    local_noon = datetime(year, month, day, 12, 0, tzinfo=ZoneInfo(tz_name))
    dst = local_noon.dst()
    return bool(dst and dst.total_seconds() != 0)


def is_us_uk_dst_mismatch_day(session_date: str, session_tz: str) -> bool:
    if session_tz != LONDON_TZ:
        return False
    return _is_dst_at_noon(session_date, LONDON_TZ) != _is_dst_at_noon(session_date, NEW_YORK_TZ)


def is_trading_day_excluded(session_date: str, session_tz: str, exclude_windows: tuple[str, ...] | list[str]) -> bool:
    for window in exclude_windows:
        if window == US_UK_DST_MISMATCH:
            if is_us_uk_dst_mismatch_day(session_date, session_tz):
                return True
            continue
        raise ValueError(f"Unsupported exclude_window: {window}")
    return False


__all__ = [
    "NEW_YORK_TZ",
    "SUPPORTED_EXCLUDE_WINDOWS",
    "US_UK_DST_MISMATCH",
    "is_trading_day_excluded",
    "is_us_uk_dst_mismatch_day",
]
