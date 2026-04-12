from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_local(utc_dt: datetime, tz_name: str) -> datetime:
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    return utc_dt.astimezone(ZoneInfo(tz_name))


def hhmm(local_dt: datetime) -> str:
    return local_dt.strftime("%H%M")


def local_clock_matches(utc_dt: datetime, tz_name: str, clock_hhmm: str) -> bool:
    local_dt = to_local(utc_dt, tz_name)
    normalized = clock_hhmm.replace(":", "")
    return hhmm(local_dt) == normalized


def build_trigger_bucket(prefix: str, tz_name: str, utc_dt: datetime) -> str:
    local_dt = to_local(utc_dt, tz_name)
    return f"{prefix}#{tz_name}#{hhmm(local_dt)}"


def trade_date_local(utc_dt: datetime, tz_name: str) -> str:
    return to_local(utc_dt, tz_name).strftime("%Y-%m-%d")


def scheduled_local_iso(utc_dt: datetime, tz_name: str) -> str:
    return to_local(utc_dt, tz_name).isoformat()


def scheduled_clock_iso_for_date(utc_dt: datetime, tz_name: str, clock_hhmm: str) -> str:
    local_dt = to_local(utc_dt, tz_name)
    hour, minute = [int(part) for part in clock_hhmm.split(":")]
    scheduled_dt = local_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return scheduled_dt.isoformat()


def parse_oanda_time(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def ttl_epoch_seconds(base_utc: datetime, ttl_days: int) -> int:
    return int((base_utc + timedelta(days=ttl_days)).timestamp())

