from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd


BROKER_TZ = "Etc/GMT-3"
JST_TZ = "Asia/Tokyo"
LONDON_TZ = "Europe/London"


@dataclass(frozen=True)
class TimeNormalizationSummary:
    # 時刻正規化で何が起きたかを残しておく。
    # fallback や重複時計は、後段の sanity や監査ログでそのまま使う。
    row_count: int
    time_jst_missing_count: int
    time_jst_fallback_count: int
    duplicate_clock_jst_count: int
    duplicate_clock_london_count: int


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_local(utc_dt: datetime, tz_name: str) -> datetime:
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


def ensure_aware_timestamp_series(values: pd.Series, tz_name: str) -> pd.Series:
    # pandas 側で tz-aware / naive が混在しやすいので、
    # core では必ず tz-aware に正規化してから扱う。
    parsed = pd.to_datetime(values, errors="coerce")
    if getattr(parsed.dt, "tz", None) is None:
        parsed = parsed.dt.tz_localize(tz_name)
    else:
        parsed = parsed.dt.tz_convert(tz_name)
    return pd.Series(parsed, index=values.index)


def index_to_time_jst(index_values: pd.Index, broker_tz: str = BROKER_TZ) -> pd.Series:
    # 1分足 index は broker time(UTC+3) とみなし、
    # 研究憲法どおり JST へ変換する fallback として使う。
    index_ts = pd.to_datetime(index_values, errors="coerce")
    if getattr(index_ts, "tz", None) is None:
        index_ts = index_ts.tz_localize(broker_tz)
    fallback_jst = index_ts.tz_convert(JST_TZ)
    return pd.Series(fallback_jst, index=index_values)


def build_time_jst(
    raw: pd.DataFrame,
    *,
    time_jst_col: str = "Time_JST",
    broker_tz: str = BROKER_TZ,
) -> tuple[pd.Series, pd.Series]:
    # Time_JST は存在していても壊れていることがあるので、
    # 行単位で fallback し、その mask を返す。
    fallback_jst = index_to_time_jst(raw.index, broker_tz=broker_tz)

    if time_jst_col not in raw.columns:
        fallback_used = pd.Series(True, index=raw.index, dtype=bool)
        return fallback_jst, fallback_used

    parsed = ensure_aware_timestamp_series(raw[time_jst_col], JST_TZ)
    invalid_mask = parsed.isna()
    if invalid_mask.any():
        parsed = parsed.where(~invalid_mask, fallback_jst)
    fallback_used = pd.Series(invalid_mask.to_numpy(), index=raw.index, dtype=bool)
    return pd.Series(parsed, index=raw.index), fallback_used


def add_time_columns(
    raw: pd.DataFrame,
    *,
    market_tz: str = LONDON_TZ,
    time_jst_col: str = "Time_JST",
    broker_tz: str = BROKER_TZ,
) -> tuple[pd.DataFrame, TimeNormalizationSummary]:
    # 研究側の minute データはここで一度正規化し、
    # 以後は Time_JST / Time_London 由来の列だけを見る前提にする。
    out = raw.copy()
    time_jst, fallback_used = build_time_jst(out, time_jst_col=time_jst_col, broker_tz=broker_tz)

    if time_jst.isna().any():
        bad_rows = int(time_jst.isna().sum())
        raise ValueError(f"Time_JST construction failed, bad_rows={bad_rows}")

    time_market = time_jst.dt.tz_convert(market_tz)

    out["Time_JST"] = time_jst
    out["Time_JST_Fallback_Used"] = fallback_used.to_numpy(dtype=bool)
    out["Date_JST"] = out["Time_JST"].dt.strftime("%Y-%m-%d")
    out["Clock_JST"] = out["Time_JST"].dt.strftime("%H:%M")
    out["Minute_JST"] = out["Time_JST"].dt.floor("min")
    out["Weekday_JST"] = out["Time_JST"].dt.weekday.astype("int8")

    out["Time_Market"] = time_market
    out["Date_Market"] = out["Time_Market"].dt.strftime("%Y-%m-%d")
    out["Clock_Market"] = out["Time_Market"].dt.strftime("%H:%M")
    out["Minute_Market"] = out["Time_Market"].dt.floor("min")
    out["Weekday_Market"] = out["Time_Market"].dt.weekday.astype("int8")

    # 東京以外を London 基準で見る現行方針に合わせ、専用列も明示的に持つ。
    # market_tz が London 以外でも、比較や監査用に揃えておく。
    time_london = time_jst.dt.tz_convert(LONDON_TZ)
    out["Time_London"] = time_london
    out["Date_London"] = out["Time_London"].dt.strftime("%Y-%m-%d")
    out["Clock_London"] = out["Time_London"].dt.strftime("%H:%M")
    out["Minute_London"] = out["Time_London"].dt.floor("min")
    out["Weekday_London"] = out["Time_London"].dt.weekday.astype("int8")

    duplicate_clock_jst_count = int(out["Date_JST"].astype(str).str.cat(out["Clock_JST"], sep="#").duplicated().sum())
    duplicate_clock_london_count = int(
        out["Date_London"].astype(str).str.cat(out["Clock_London"], sep="#").duplicated().sum()
    )

    summary = TimeNormalizationSummary(
        row_count=int(len(out)),
        time_jst_missing_count=int(pd.to_datetime(raw.get(time_jst_col), errors="coerce").isna().sum())
        if time_jst_col in raw.columns
        else int(len(out)),
        time_jst_fallback_count=int(fallback_used.sum()),
        duplicate_clock_jst_count=duplicate_clock_jst_count,
        duplicate_clock_london_count=duplicate_clock_london_count,
    )
    return out, summary


def sort_and_deduplicate_by_clock(
    df: pd.DataFrame,
    *,
    date_col: str,
    clock_col: str,
    time_col: str,
    keep: str = "first",
) -> tuple[pd.DataFrame, int]:
    # 日次 group 化の前に時計重複を吸収する。
    # 何件捨てたかは監査対象なので返り値に含める。
    sorted_df = df.sort_values(time_col)
    before = len(sorted_df)
    deduped = sorted_df.drop_duplicates([date_col, clock_col], keep=keep)
    removed = int(before - len(deduped))
    return deduped, removed


def filter_weekdays(df: pd.DataFrame, weekday_col: str) -> pd.DataFrame:
    # 土日除外をここで共通化しておくと、series ごとの差を減らしやすい。
    return df.loc[df[weekday_col] < 5].copy()


__all__ = [
    "BROKER_TZ",
    "JST_TZ",
    "LONDON_TZ",
    "TimeNormalizationSummary",
    "add_time_columns",
    "build_time_jst",
    "build_trigger_bucket",
    "ensure_aware_timestamp_series",
    "filter_weekdays",
    "hhmm",
    "index_to_time_jst",
    "local_clock_matches",
    "parse_oanda_time",
    "scheduled_clock_iso_for_date",
    "scheduled_local_iso",
    "sort_and_deduplicate_by_clock",
    "to_local",
    "trade_date_local",
    "ttl_epoch_seconds",
    "utc_now",
]
