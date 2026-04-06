from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from timer_entry.minute_data import _normalize_event_time_columns
from timer_entry.time_utils import LONDON_TZ, add_time_columns


def _build_raw_frame() -> pd.DataFrame:
    index = pd.Index(
        [
            "2024-01-10 00:00:00",
            "2024-01-10 00:01:00",
        ]
    )
    return pd.DataFrame(
        {
            "Time_JST": [
                "2024-01-10 06:00:00+09:00",
                "2024-01-10 06:01:00+09:00",
            ],
            "Bid_Open": [100.00, 100.01],
            "Bid_High": [100.03, 100.04],
            "Bid_High_Time": [
                "2024-01-09 21:00:10",
                "2024-01-09 21:01:05+00:00",
            ],
            "Bid_Low": [99.99, 100.00],
            "Bid_Low_Time": [
                "2024-01-09 21:00:45",
                "2024-01-09 21:01:40+00:00",
            ],
            "Bid_Close": [100.02, 100.03],
            "Ask_Open": [100.02, 100.03],
            "Ask_High": [100.05, 100.06],
            "Ask_High_Time": [
                "2024-01-09 21:00:12",
                "2024-01-09 21:01:07+00:00",
            ],
            "Ask_Low": [100.01, 100.02],
            "Ask_Low_Time": [
                "2024-01-09 21:00:42",
                "2024-01-09 21:01:35+00:00",
            ],
            "Ask_Close": [100.04, 100.05],
        },
        index=index,
    )


def test_normalize_event_time_columns_returns_london_tz() -> None:
    raw = _build_raw_frame()
    normalized = _normalize_event_time_columns(raw)

    for column in ("Bid_High_Time", "Bid_Low_Time", "Ask_High_Time", "Ask_Low_Time"):
        series = normalized[column]
        assert str(series.dt.tz) == LONDON_TZ


def test_add_time_columns_builds_market_time_from_time_jst() -> None:
    raw = _build_raw_frame()
    normalized = _normalize_event_time_columns(raw)
    frame, summary = add_time_columns(normalized, market_tz="Europe/London")

    assert summary.row_count == 2
    assert summary.time_jst_fallback_count == 0
    assert frame.loc[frame.index[0], "Clock_JST"] == "06:00"
    assert frame.loc[frame.index[0], "Clock_Market"] == "21:00"
    assert str(frame.loc[frame.index[0], "Time_Market"].tzinfo) == LONDON_TZ


def test_event_times_stay_within_their_market_minute_bar() -> None:
    raw = _build_raw_frame()
    normalized = _normalize_event_time_columns(raw)
    frame, _ = add_time_columns(normalized, market_tz="Europe/London")

    for _, row in frame.iterrows():
        minute_start = pd.Timestamp(row["Minute_Market"])
        minute_end = minute_start + pd.Timedelta(minutes=1)
        for column in ("Bid_High_Time", "Bid_Low_Time", "Ask_High_Time", "Ask_Low_Time"):
            event_time = pd.Timestamp(row[column])
            assert minute_start <= event_time < minute_end


def test_add_time_columns_uses_index_fallback_for_invalid_time_jst() -> None:
    raw = _build_raw_frame()
    raw.loc[raw.index[1], "Time_JST"] = "broken_timestamp"
    normalized = _normalize_event_time_columns(raw)
    frame, summary = add_time_columns(normalized, market_tz="Europe/London")

    assert summary.time_jst_fallback_count == 1
    assert bool(frame.loc[frame.index[1], "Time_JST_Fallback_Used"]) is True
    assert frame.loc[frame.index[1], "Clock_JST"] == "06:01"
