from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

import pandas as pd

from .time_utils import (
    LONDON_TZ,
    TimeNormalizationSummary,
    add_time_columns,
    filter_weekdays,
    sort_and_deduplicate_by_clock,
)


SessionTz = Literal["Asia/Tokyo", "Europe/London"]

REQUIRED_MINUTE_COLUMNS = (
    "Bid_Open",
    "Bid_High",
    "Bid_High_Time",
    "Bid_Low",
    "Bid_Low_Time",
    "Bid_Close",
    "Ask_Open",
    "Ask_High",
    "Ask_High_Time",
    "Ask_Low",
    "Ask_Low_Time",
    "Ask_Close",
)

PRICE_COLUMNS = (
    "Bid_Open",
    "Bid_High",
    "Bid_Low",
    "Bid_Close",
    "Ask_Open",
    "Ask_High",
    "Ask_Low",
    "Ask_Close",
)

EVENT_TIME_COLUMNS = (
    "Bid_High_Time",
    "Bid_Low_Time",
    "Ask_High_Time",
    "Ask_Low_Time",
)


@dataclass(frozen=True)
class TradingDay:
    # 東京系・ロンドン系の両方で使えるように、
    # session date と session timezone を明示して持つ。
    session_date: str
    session_tz: SessionTz
    year: int
    weekday: int
    frame: pd.DataFrame


@dataclass(frozen=True)
class MinuteDataSummary:
    # loader 層で起きたことは後から辿れるように集約する。
    year_count: int
    row_count: int
    session_day_count: int
    time_jst_missing_count: int
    time_jst_fallback_count: int
    duplicate_clock_jst_count: int
    duplicate_clock_london_count: int
    duplicate_clock_removed_count: int


def _validate_required_columns(df: pd.DataFrame, *, year: int) -> None:
    missing = [col for col in REQUIRED_MINUTE_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"missing required columns for year={year}: {missing}")


def _normalize_price_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in PRICE_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce").astype("float32")
    return out


def _normalize_event_time_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    def _normalize_one(value: object) -> pd.Timestamp:
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return pd.NaT
        if parsed.tzinfo is None:
            return parsed.tz_localize(LONDON_TZ, nonexistent="NaT", ambiguous="NaT")
        return parsed.tz_convert(LONDON_TZ)

    for col in EVENT_TIME_COLUMNS:
        out[col] = out[col].map(_normalize_one)
    return out


def _normalize_year_frame(
    raw: pd.DataFrame,
    *,
    year: int,
    market_tz: SessionTz,
) -> tuple[pd.DataFrame, TimeNormalizationSummary]:
    _validate_required_columns(raw, year=year)
    df = _normalize_price_columns(raw)
    df = _normalize_event_time_columns(df)
    df, summary = add_time_columns(df, market_tz=market_tz)
    return df, summary


def load_year_frame(
    year: int,
    *,
    dataset_dir: str | Path = "dataset",
    market_tz: SessionTz = "Asia/Tokyo",
) -> tuple[pd.DataFrame, TimeNormalizationSummary]:
    # 年次ファイルの読み込みと正規化をここで完了させる。
    path = Path(dataset_dir) / f"{year}_1min.pkl.gz"
    if not path.exists():
        raise FileNotFoundError(f"minute dataset not found: {path}")

    raw = pd.read_pickle(path)
    df, summary = _normalize_year_frame(raw, year=year, market_tz=market_tz)
    sort_col = "Time_JST" if market_tz == "Asia/Tokyo" else "Time_London"
    return df.sort_values(sort_col).reset_index(drop=True), summary


def _session_columns(session_tz: SessionTz) -> tuple[str, str, str]:
    if session_tz == "Asia/Tokyo":
        return "Date_JST", "Clock_JST", "Time_JST"
    return "Date_London", "Clock_London", "Time_London"


def load_trading_days(
    years: Iterable[int],
    *,
    dataset_dir: str | Path = "dataset",
    session_tz: SessionTz = "Asia/Tokyo",
) -> tuple[list[TradingDay], MinuteDataSummary]:
    # 日次単位の TradingDay へ切り分ける。
    # 時刻 fallback や重複時計の除去件数もここで集計する。
    date_col, clock_col, time_col = _session_columns(session_tz)
    weekday_col = "Weekday_JST" if session_tz == "Asia/Tokyo" else "Weekday_London"

    days: list[TradingDay] = []
    year_count = 0
    row_count = 0
    time_jst_missing_count = 0
    time_jst_fallback_count = 0
    duplicate_clock_jst_count = 0
    duplicate_clock_london_count = 0
    duplicate_clock_removed_count = 0

    for year in years:
        df, summary = load_year_frame(year, dataset_dir=dataset_dir, market_tz=session_tz)
        year_count += 1
        row_count += summary.row_count
        time_jst_missing_count += summary.time_jst_missing_count
        time_jst_fallback_count += summary.time_jst_fallback_count
        duplicate_clock_jst_count += summary.duplicate_clock_jst_count
        duplicate_clock_london_count += summary.duplicate_clock_london_count

        weekday_filtered = filter_weekdays(df, weekday_col)
        for session_date, day_df in weekday_filtered.groupby(date_col, sort=True):
            deduped, removed = sort_and_deduplicate_by_clock(
                day_df,
                date_col=date_col,
                clock_col=clock_col,
                time_col=time_col,
            )
            duplicate_clock_removed_count += removed
            if deduped.empty:
                continue

            weekday = int(deduped[weekday_col].iloc[0])
            indexed = deduped.set_index(clock_col, drop=False)
            days.append(
                TradingDay(
                    session_date=str(session_date),
                    session_tz=session_tz,
                    year=year,
                    weekday=weekday,
                    frame=indexed,
                )
            )

    days.sort(key=lambda item: item.session_date)
    summary = MinuteDataSummary(
        year_count=year_count,
        row_count=row_count,
        session_day_count=len(days),
        time_jst_missing_count=time_jst_missing_count,
        time_jst_fallback_count=time_jst_fallback_count,
        duplicate_clock_jst_count=duplicate_clock_jst_count,
        duplicate_clock_london_count=duplicate_clock_london_count,
        duplicate_clock_removed_count=duplicate_clock_removed_count,
    )
    return days, summary


__all__ = [
    "EVENT_TIME_COLUMNS",
    "MinuteDataSummary",
    "PRICE_COLUMNS",
    "REQUIRED_MINUTE_COLUMNS",
    "SessionTz",
    "TradingDay",
    "load_trading_days",
    "load_year_frame",
]
