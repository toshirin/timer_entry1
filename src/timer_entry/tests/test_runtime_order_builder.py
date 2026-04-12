from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "runtime" / "src"))

from timer_entry_runtime.models import PriceSnapshot, SettingConfig
from timer_entry_runtime.order_builder import (
    protection_levels,
    requested_entry_from_snapshot,
    trade_protection_order_body,
)


def _setting(side: str, *, tp_pips: float = 10.0, sl_pips: float = 30.0) -> SettingConfig:
    return SettingConfig(
        setting_id=f"test_{side}",
        enabled=True,
        strategy_id=f"timed_entry_{side}",
        slot_id="tyo09",
        market_session="tokyo",
        market_tz="Asia/Tokyo",
        instrument="USD_JPY",
        side=side,
        entry_clock_local="09:25",
        forced_exit_clock_local="10:00",
        trigger_bucket_entry="ENTRY#Asia/Tokyo#0925",
        trigger_bucket_exit="EXIT#Asia/Tokyo#1000",
        fixed_units=10,
        margin_ratio_target=None,
        size_scale_pct=None,
        tp_pips=tp_pips,
        sl_pips=sl_pips,
        research_label=None,
        market_open_check_seconds=10,
        max_concurrent_positions=1,
        kill_switch_dd_pct=-0.2,
        kill_switch_reference_balance_jpy=100000.0,
        min_maintenance_margin_pct=150.0,
        filter_spec_json=None,
        execution_spec_json=None,
        notes=None,
    )


def _snapshot() -> PriceSnapshot:
    return PriceSnapshot(
        instrument="USD_JPY",
        bid=149.990,
        ask=150.005,
        time_utc=datetime(2026, 4, 12, tzinfo=timezone.utc),
    )


def test_requested_entry_uses_ask_for_buy_and_bid_for_sell() -> None:
    buy_entry = requested_entry_from_snapshot(_setting("buy"), _snapshot())
    sell_entry = requested_entry_from_snapshot(_setting("sell"), _snapshot())

    assert buy_entry.price_side == "ask"
    assert buy_entry.price == 150.005
    assert sell_entry.price_side == "bid"
    assert sell_entry.price == 149.990


def test_buy_protection_uses_bid_tp_and_ask_sl_from_fill_price() -> None:
    levels = protection_levels(_setting("buy", tp_pips=10.0, sl_pips=30.0), entry_fill_price=150.0)
    body = trade_protection_order_body(_setting("buy", tp_pips=10.0, sl_pips=30.0), entry_fill_price=150.0)

    assert levels.tp_trigger_side == "bid"
    assert levels.sl_trigger_side == "ask"
    assert round(levels.tp_trigger_price, 3) == 150.100
    assert round(levels.sl_trigger_price, 3) == 149.700
    assert body["takeProfit"]["triggerCondition"] == "BID"  # type: ignore[index]
    assert body["stopLoss"]["triggerCondition"] == "ASK"  # type: ignore[index]


def test_sell_protection_uses_ask_tp_and_bid_sl_from_fill_price() -> None:
    levels = protection_levels(_setting("sell", tp_pips=20.0, sl_pips=5.0), entry_fill_price=150.0)
    body = trade_protection_order_body(_setting("sell", tp_pips=20.0, sl_pips=5.0), entry_fill_price=150.0)

    assert levels.tp_trigger_side == "ask"
    assert levels.sl_trigger_side == "bid"
    assert round(levels.tp_trigger_price, 3) == 149.800
    assert round(levels.sl_trigger_price, 3) == 150.050
    assert body["takeProfit"]["triggerCondition"] == "ASK"  # type: ignore[index]
    assert body["stopLoss"]["triggerCondition"] == "BID"  # type: ignore[index]

