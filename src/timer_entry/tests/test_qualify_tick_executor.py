from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from qualify.common.tick_replay.tick_executor import TickReplayRequest, execute_tick_replay


def _epoch_us(ts_local: str, market_tz: str) -> int:
    return int(pd.Timestamp(ts_local, tz=market_tz).tz_convert("UTC").value // 1_000)


def test_tick_executor_buy_respects_next_minute_monitoring_and_bid_ask() -> None:
    ticks = pd.DataFrame(
        [
            {"epoch_us": _epoch_us("2024-01-02 09:25:01", "Asia/Tokyo"), "bid": 99.99, "ask": 100.00},
            {"epoch_us": _epoch_us("2024-01-02 09:25:30", "Asia/Tokyo"), "bid": 99.70, "ask": 99.69},
            {"epoch_us": _epoch_us("2024-01-02 09:26:05", "Asia/Tokyo"), "bid": 100.06, "ask": 100.07},
        ]
    )
    request = TickReplayRequest(
        trade_id="t1",
        date_local="2024-01-02",
        year=2024,
        comparison_label="buy0925_all_tp5_sl15_fx0945",
        side="buy",
        market_tz="Asia/Tokyo",
        filter_label="all",
        entry_time_local="2024-01-02 09:25:00",
        forced_exit_time_local="2024-01-02 09:45:00",
        tp_pips=5.0,
        sl_pips=15.0,
    )

    result = execute_tick_replay(request, ticks)

    assert result["exit_reason"] == "tp"
    assert result["entry_price"] == 100.00
    assert result["exit_price"] == 100.06
    assert result["pnl_pips"] == 6.0
    assert result["entry_price_series"] == "ask_tick"
    assert result["exit_price_series"] == "bid_tick"
    assert result["entry_bar_exit_flag"] is False


def test_tick_executor_sell_uses_bid_entry_and_ask_exit() -> None:
    ticks = pd.DataFrame(
        [
            {"epoch_us": _epoch_us("2024-01-02 10:10:02", "Asia/Tokyo"), "bid": 150.00, "ask": 150.02},
            {"epoch_us": _epoch_us("2024-01-02 10:11:00", "Asia/Tokyo"), "bid": 149.77, "ask": 149.79},
        ]
    )
    request = TickReplayRequest(
        trade_id="t2",
        date_local="2024-01-02",
        year=2024,
        comparison_label="sell1010_all_tp20_sl5_fx1045",
        side="sell",
        market_tz="Asia/Tokyo",
        filter_label="all",
        entry_time_local="2024-01-02 10:10:00",
        forced_exit_time_local="2024-01-02 10:45:00",
        tp_pips=20.0,
        sl_pips=5.0,
    )

    result = execute_tick_replay(request, ticks)

    assert result["exit_reason"] == "tp"
    assert result["entry_price"] == 150.00
    assert result["exit_price"] == 149.79
    assert result["pnl_pips"] == 21.0
    assert result["entry_price_series"] == "bid_tick"
    assert result["exit_price_series"] == "ask_tick"
