from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from timer_entry.backtest_1m import run_backtest_1m
from timer_entry.backtest_fast import preprocess_fast_days, run_scan_fast
from timer_entry.minute_data import TradingDay
from timer_entry.schemas import StrategySetting


def _build_day_frame(
    *,
    session_tz: str = "Asia/Tokyo",
    date_text: str = "2024-01-10",
    start_clock: str = "09:05",
    end_clock: str = "10:55",
) -> pd.DataFrame:
    start_ts = pd.Timestamp(f"{date_text} {start_clock}", tz=session_tz)
    end_ts = pd.Timestamp(f"{date_text} {end_clock}", tz=session_tz)
    minute_index = pd.date_range(start=start_ts, end=end_ts, freq="1min")

    rows: list[dict[str, object]] = []
    base_price = 100.00
    spread = 0.02
    for idx, minute_ts in enumerate(minute_index):
        bid_open = base_price + idx * 0.01
        bid_close = bid_open + 0.01
        ask_open = bid_open + spread
        ask_close = bid_close + spread
        rows.append(
            {
                "Clock_JST": minute_ts.strftime("%H:%M"),
                "Minute_JST": minute_ts,
                "Clock_London": minute_ts.strftime("%H:%M"),
                "Minute_London": minute_ts,
                "Clock_Market": minute_ts.strftime("%H:%M"),
                "Minute_Market": minute_ts,
                "Bid_Open": bid_open,
                "Bid_High": bid_close + 0.01,
                "Bid_High_Time": minute_ts + timedelta(seconds=10),
                "Bid_Low": bid_open - 0.01,
                "Bid_Low_Time": minute_ts + timedelta(seconds=50),
                "Bid_Close": bid_close,
                "Ask_Open": ask_open,
                "Ask_High": ask_close + 0.01,
                "Ask_High_Time": minute_ts + timedelta(seconds=10),
                "Ask_Low": ask_open - 0.01,
                "Ask_Low_Time": minute_ts + timedelta(seconds=50),
                "Ask_Close": ask_close,
            }
        )

    frame = pd.DataFrame(rows)
    return frame.set_index("Clock_JST", drop=False)


def _build_trading_day() -> TradingDay:
    return TradingDay(
        session_date="2024-01-10",
        session_tz="Asia/Tokyo",
        year=2024,
        weekday=2,
        frame=_build_day_frame(),
    )


def _set_minute(frame: pd.DataFrame, clock_hhmm: str, **updates: object) -> None:
    for key, value in updates.items():
        frame.loc[clock_hhmm, key] = value


def _build_setting(
    *,
    side: str,
    tp_pips: float,
    sl_pips: float,
    entry_clock_local: str = "10:00",
    forced_exit_clock_local: str = "10:55",
) -> StrategySetting:
    return StrategySetting(
        setting_id=f"test_{side}_{entry_clock_local.replace(':', '')}",
        slot_id="tyo10",
        side=side,  # type: ignore[arg-type]
        market_tz="Asia/Tokyo",
        entry_clock_local=entry_clock_local,
        forced_exit_clock_local=forced_exit_clock_local,
        tp_pips=tp_pips,
        sl_pips=sl_pips,
        filter_labels=("all",),
    )


def _run_both(day: TradingDay, setting: StrategySetting) -> tuple[object, pd.Series, pd.Series]:
    slow = run_backtest_1m([day], setting)
    prepared = preprocess_fast_days([day])
    exit_after_minutes = (
        pd.Timestamp(f"2000-01-01 {setting.normalized_forced_exit_clock()}")
        - pd.Timestamp(f"2000-01-01 {setting.normalized_entry_clock()}")
    )
    fast = run_scan_fast(
        prepared,
        slot_id=setting.slot_id,
        side=setting.side,
        entry_clock_local=setting.normalized_entry_clock(),
        exit_after_minutes=int(exit_after_minutes.total_seconds() / 60.0),
        sl_grid_pips=[setting.sl_pips],
        tp_grid_pips=[setting.tp_pips],
        pre_range_median=setting.pre_range_threshold if setting.pre_range_threshold is not None else 0.1,
    )
    fast_row = fast.daily_df.loc[
        (fast.daily_df["filter_label"] == "all")
        & (fast.daily_df["sl_pips"] == float(setting.sl_pips))
        & (fast.daily_df["tp_pips"] == float(setting.tp_pips))
    ].iloc[0]
    fast_summary_row = fast.summary_df.loc[
        (fast.summary_df["filter_label"] == "all")
        & (fast.summary_df["sl_pips"] == float(setting.sl_pips))
        & (fast.summary_df["tp_pips"] == float(setting.tp_pips))
    ].iloc[0]
    return slow, fast_row, fast_summary_row


def _assert_trade_matches(slow_result: object, fast_row: pd.Series, fast_summary_row: pd.Series) -> None:
    trades = slow_result.trades  # type: ignore[attr-defined]
    assert len(trades) == 1
    trade = trades[0]
    assert trade.exit_reason == fast_row["exit_reason"]
    assert trade.hold_minutes == int(fast_row["hold_min"])
    assert trade.filter_label == fast_row["filter_label"]
    assert trade.notes.startswith(f"conflict_resolved_by={fast_row['conflict_resolved_by']}")
    assert trade.pnl_pips == pytest.approx(float(fast_row["pnl_pips"]), abs=1e-6)

    summary = slow_result.summary  # type: ignore[attr-defined]
    assert summary.trade_count == 1
    assert summary.gross_pips == pytest.approx(float(fast_row["pnl_pips"]), abs=1e-6)
    assert summary.trade_count == int(fast_summary_row["trade_count"])
    assert summary.gross_pips == pytest.approx(float(fast_summary_row["gross_pips"]), abs=1e-6)


def test_backtest_parity_buy_tp() -> None:
    day = _build_trading_day()
    setting = _build_setting(side="buy", tp_pips=3.0, sl_pips=5.0)

    entry_ask = float(day.frame.loc["10:00", "Ask_Open"])
    tp_price_bid = entry_ask + 3.0 * 0.01
    _set_minute(day.frame, "10:01", Bid_High=tp_price_bid + 0.01, Bid_High_Time=pd.Timestamp("2024-01-10 10:01:05", tz="Asia/Tokyo"))

    slow, fast_row, fast_summary_row = _run_both(day, setting)
    _assert_trade_matches(slow, fast_row, fast_summary_row)
    assert fast_row["exit_reason"] == "tp"
    assert bool(fast_row["same_bar_conflict_flag"]) is False


def test_backtest_parity_buy_same_bar_unresolved_prefers_sl() -> None:
    day = _build_trading_day()
    setting = _build_setting(side="buy", tp_pips=3.0, sl_pips=5.0)

    entry_ask = float(day.frame.loc["10:00", "Ask_Open"])
    entry_bid = float(day.frame.loc["10:00", "Bid_Open"])
    entry_spread = entry_ask - entry_bid
    tp_price_bid = entry_ask + 3.0 * 0.01
    sl_trigger_ask = entry_ask - 5.0 * 0.01
    expected_exit_bid = sl_trigger_ask - entry_spread
    expected_pnl = (expected_exit_bid - entry_ask) / 0.01

    same_time = pd.Timestamp("2024-01-10 10:01:20", tz="Asia/Tokyo")
    _set_minute(
        day.frame,
        "10:01",
        Bid_High=tp_price_bid + 0.01,
        Ask_Low=sl_trigger_ask - 0.01,
        Bid_High_Time=same_time,
        Ask_Low_Time=same_time,
    )

    slow, fast_row, fast_summary_row = _run_both(day, setting)
    _assert_trade_matches(slow, fast_row, fast_summary_row)
    assert fast_row["exit_reason"] == "sl"
    assert fast_row["conflict_resolved_by"] == "unfavorable_side"
    assert bool(fast_row["same_bar_conflict_flag"]) is True
    assert bool(fast_row["same_bar_unresolved_flag"]) is True
    assert float(fast_row["pnl_pips"]) == pytest.approx(expected_pnl, abs=1e-6)


def test_backtest_parity_buy_same_bar_tp_first_by_event_time() -> None:
    day = _build_trading_day()
    setting = _build_setting(side="buy", tp_pips=3.0, sl_pips=5.0)

    entry_ask = float(day.frame.loc["10:00", "Ask_Open"])
    tp_price_bid = entry_ask + 3.0 * 0.01
    sl_trigger_ask = entry_ask - 5.0 * 0.01

    _set_minute(
        day.frame,
        "10:01",
        Bid_High=tp_price_bid + 0.01,
        Ask_Low=sl_trigger_ask - 0.01,
        Bid_High_Time=pd.Timestamp("2024-01-10 10:01:05", tz="Asia/Tokyo"),
        Ask_Low_Time=pd.Timestamp("2024-01-10 10:01:45", tz="Asia/Tokyo"),
    )

    slow, fast_row, fast_summary_row = _run_both(day, setting)
    _assert_trade_matches(slow, fast_row, fast_summary_row)
    assert fast_row["exit_reason"] == "tp"
    assert fast_row["conflict_resolved_by"] == "event_time_tp_first"
    assert bool(fast_row["same_bar_conflict_flag"]) is True
    assert bool(fast_row["same_bar_unresolved_flag"]) is False


def test_backtest_parity_sell_conservative_sl() -> None:
    day = _build_trading_day()
    setting = _build_setting(side="sell", tp_pips=3.0, sl_pips=5.0)

    entry_bid = float(day.frame.loc["10:00", "Bid_Open"])
    entry_ask = float(day.frame.loc["10:00", "Ask_Open"])
    entry_spread = entry_ask - entry_bid
    sl_trigger_bid = entry_bid + 5.0 * 0.01
    expected_exit_ask = sl_trigger_bid + entry_spread
    expected_pnl = (entry_bid - expected_exit_ask) / 0.01

    _set_minute(
        day.frame,
        "10:01",
        Bid_High=sl_trigger_bid + 0.01,
        Bid_High_Time=pd.Timestamp("2024-01-10 10:01:10", tz="Asia/Tokyo"),
    )

    slow, fast_row, fast_summary_row = _run_both(day, setting)
    _assert_trade_matches(slow, fast_row, fast_summary_row)
    assert fast_row["exit_reason"] == "sl"
    assert fast_row["conflict_resolved_by"] == "single_hit_sl"
    assert float(fast_row["pnl_pips"]) == pytest.approx(expected_pnl, abs=1e-6)


def test_backtest_parity_sell_tp() -> None:
    day = _build_trading_day()
    setting = _build_setting(side="sell", tp_pips=3.0, sl_pips=5.0)

    entry_bid = float(day.frame.loc["10:00", "Bid_Open"])
    tp_price_ask = entry_bid - 3.0 * 0.01
    _set_minute(day.frame, "10:01", Ask_Low=tp_price_ask - 0.01, Ask_Low_Time=pd.Timestamp("2024-01-10 10:01:05", tz="Asia/Tokyo"))

    slow, fast_row, fast_summary_row = _run_both(day, setting)
    _assert_trade_matches(slow, fast_row, fast_summary_row)
    assert fast_row["exit_reason"] == "tp"
    assert fast_row["conflict_resolved_by"] == "single_hit_tp"


def test_backtest_parity_forced_exit() -> None:
    day = _build_trading_day()
    setting = _build_setting(side="buy", tp_pips=300.0, sl_pips=300.0)

    slow, fast_row, fast_summary_row = _run_both(day, setting)
    _assert_trade_matches(slow, fast_row, fast_summary_row)
    assert fast_row["exit_reason"] == "forced_exit"
    assert fast_row["conflict_resolved_by"] == "forced_exit"


def test_backtest_fast_uses_clock_for_forced_exit_with_missing_inner_bar() -> None:
    frame = _build_day_frame()
    frame = frame.drop(index="10:30")
    day = TradingDay(
        session_date="2024-01-10",
        session_tz="Asia/Tokyo",
        year=2024,
        weekday=2,
        frame=frame,
    )
    setting = _build_setting(side="buy", tp_pips=300.0, sl_pips=300.0)

    slow = run_backtest_1m([day], setting)
    fast = run_scan_fast(
        preprocess_fast_days([day]),
        slot_id=setting.slot_id,
        side=setting.side,
        entry_clock_local=setting.normalized_entry_clock(),
        exit_after_minutes=55,
        sl_grid_pips=[setting.sl_pips],
        tp_grid_pips=[setting.tp_pips],
        pre_range_median=0.1,
    )

    fast_row = fast.daily_df.loc[
        (fast.daily_df["filter_label"] == "all")
        & (fast.daily_df["sl_pips"] == float(setting.sl_pips))
        & (fast.daily_df["tp_pips"] == float(setting.tp_pips))
    ].iloc[0]
    fast_summary_row = fast.summary_df.loc[
        (fast.summary_df["filter_label"] == "all")
        & (fast.summary_df["sl_pips"] == float(setting.sl_pips))
        & (fast.summary_df["tp_pips"] == float(setting.tp_pips))
    ].iloc[0]
    _assert_trade_matches(slow, fast_row, fast_summary_row)
    assert int(fast_row["hold_min"]) == 55


def test_backtest_parity_vol_ge_med_filter() -> None:
    day = _build_trading_day()
    setting = StrategySetting(
        setting_id="test_buy_vol",
        slot_id="tyo10",
        side="buy",
        market_tz="Asia/Tokyo",
        entry_clock_local="10:00",
        forced_exit_clock_local="10:55",
        tp_pips=300.0,
        sl_pips=300.0,
        filter_labels=("vol_ge_med",),
        pre_range_threshold=0.1,
    )

    slow = run_backtest_1m([day], setting)
    prepared = preprocess_fast_days([day])
    fast = run_scan_fast(
        prepared,
        slot_id=setting.slot_id,
        side=setting.side,
        entry_clock_local=setting.normalized_entry_clock(),
        exit_after_minutes=55,
        sl_grid_pips=[setting.sl_pips],
        tp_grid_pips=[setting.tp_pips],
        pre_range_median=setting.pre_range_threshold,
    )
    fast_row = fast.daily_df.loc[fast.daily_df["filter_label"] == "vol_ge_med"].iloc[0]
    fast_summary_row = fast.summary_df.loc[fast.summary_df["filter_label"] == "vol_ge_med"].iloc[0]
    _assert_trade_matches(slow, fast_row, fast_summary_row)


def test_backtest_parity_london_session() -> None:
    frame = _build_day_frame(session_tz="Europe/London", date_text="2024-01-10", start_clock="08:05", end_clock="09:55")
    day = TradingDay(
        session_date="2024-01-10",
        session_tz="Europe/London",
        year=2024,
        weekday=2,
        frame=frame.set_index("Clock_Market", drop=False),
    )
    setting = StrategySetting(
        setting_id="test_london_buy",
        slot_id="lon09",
        side="buy",
        market_tz="Europe/London",
        entry_clock_local="09:00",
        forced_exit_clock_local="09:55",
        tp_pips=300.0,
        sl_pips=300.0,
        filter_labels=("all",),
    )

    slow, fast_row, fast_summary_row = _run_both(day, setting)
    _assert_trade_matches(slow, fast_row, fast_summary_row)
