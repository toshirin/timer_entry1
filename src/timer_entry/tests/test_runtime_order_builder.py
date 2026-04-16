from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "runtime" / "src"))

from timer_entry_runtime.filtering import evaluate_filters
from timer_entry_runtime.models import Candle, PriceSnapshot, SettingConfig
from timer_entry_runtime.models import AccountSnapshot, OrderResult
from timer_entry_runtime.order_builder import (
    protection_levels,
    requested_entry_from_snapshot,
    trade_protection_order_body,
)
from timer_entry_runtime.runtime import _create_entry_trade
from timer_entry_runtime.sizing import compute_units


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
        labels=[],
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


def test_margin_price_uses_ask_for_buy_and_sell() -> None:
    account = AccountSnapshot(account_id="dummy", balance=100_000.0)

    buy_sizing = compute_units(setting=_setting("buy"), account=account, price=_snapshot())
    sell_sizing = compute_units(setting=_setting("sell"), account=account, price=_snapshot())

    assert buy_sizing.margin_price_side == "ask"
    assert buy_sizing.margin_price == 150.005
    assert sell_sizing.margin_price_side == "ask"
    assert sell_sizing.margin_price == 150.005


def test_runtime_filter_supports_opposite_sign_right_strength_balance() -> None:
    setting = SettingConfig(
        **{
            **_setting("buy").__dict__,
            "filter_spec_json": json.dumps(
                [
                    {
                        "filter_type": "shape_balance",
                        "mode": "opposite_sign_right_strength_balance",
                        "operator": "ge",
                        "threshold": 4.0,
                    }
                ],
                separators=(",", ":"),
            ),
        }
    )
    candles = [
        Candle(
            time_utc=datetime(2024, 1, 1, 23, 30, tzinfo=timezone.utc),
            bid_open=150.00,
            bid_high=150.00,
            bid_low=149.99,
            bid_close=149.99,
            complete=True,
        ),
        Candle(
            time_utc=datetime(2024, 1, 1, 23, 55, tzinfo=timezone.utc),
            bid_open=150.00,
            bid_high=150.05,
            bid_low=149.99,
            bid_close=149.99,
            complete=True,
        ),
        Candle(
            time_utc=datetime(2024, 1, 2, 0, 20, tzinfo=timezone.utc),
            bid_open=150.00,
            bid_high=150.05,
            bid_low=150.00,
            bid_close=150.05,
            complete=True,
        ),
    ]

    decisions = evaluate_filters(
        setting=setting,
        now_utc=datetime(2024, 1, 2, 0, 25, tzinfo=timezone.utc),
        candles=candles,
    )

    assert decisions[0].passed is True
    assert decisions[0].values["opposite_sign"] is True
    assert round(float(decisions[0].values["right_strength_balance_pips"]), 6) == 4.0


def test_runtime_trend_ratio_zero_range_does_not_pass_range_lt_filter() -> None:
    setting = SettingConfig(
        **{
            **_setting("buy").__dict__,
            "filter_spec_json": json.dumps(
                [
                    {
                        "filter_type": "trend_ratio",
                        "operator": "lt",
                        "threshold": 0.25,
                        "lookback_start_min": 55,
                        "lookback_end_min": 5,
                    }
                ],
                separators=(",", ":"),
            ),
        }
    )
    start_utc = datetime(2024, 1, 1, 23, 30, tzinfo=timezone.utc)
    candles = [
        Candle(
            time_utc=start_utc + timedelta(minutes=offset),
            bid_open=150.00,
            bid_high=150.00,
            bid_low=150.00,
            bid_close=150.00,
            complete=True,
        )
        for offset in range(51)
    ]

    decisions = evaluate_filters(
        setting=setting,
        now_utc=datetime(2024, 1, 2, 0, 25, tzinfo=timezone.utc),
        candles=candles,
    )

    assert decisions[0].passed is False
    assert math.isnan(float(decisions[0].values["trend_ratio"]))
    assert decisions[0].values["threshold"] == 0.25


def test_tp_sl_failure_keeps_trade_state_entered_for_forced_exit() -> None:
    class FakeAws:
        def __init__(self) -> None:
            self.trade_updates: list[dict[str, object]] = []
            self.execution_updates: list[dict[str, object]] = []
            self.decisions: list[dict[str, object]] = []

        def build_trade_state_seed(self, **kwargs: object) -> dict[str, object]:
            return dict(kwargs)

        def create_trade_state_if_absent(self, item: dict[str, object]) -> bool:
            return True

        def build_execution_log_seed(self, **kwargs: object) -> dict[str, object]:
            return dict(kwargs)

        def create_execution_log(self, item: dict[str, object]) -> None:
            pass

        def update_execution_log(self, execution_id: str, **attributes: object) -> None:
            self.execution_updates.append({"execution_id": execution_id, **attributes})

        def update_trade_state(self, trade_id: str, **attributes: object) -> None:
            self.trade_updates.append({"trade_id": trade_id, **attributes})

        def query_trade_states_for_setting(self, setting_id: str) -> list[dict[str, object]]:
            return []

        def build_decision_log_seed(self, **kwargs: object) -> dict[str, object]:
            return dict(kwargs)

        def create_decision_log(self, item: dict[str, object]) -> None:
            self.decisions.append(item)

    class FakeOanda:
        def get_account_snapshot(self) -> AccountSnapshot:
            return AccountSnapshot(account_id="dummy", balance=100_000.0)

        def create_market_order(self, **kwargs: object) -> OrderResult:
            return OrderResult(
                order_id="order-1",
                trade_id="trade-1",
                fill_price=150.0,
                client_id="client-1",
                raw_response={"orderFillTransaction": {"time": "2026-04-12T00:00:01Z"}},
            )

        def set_trade_protection_orders(self, **kwargs: object) -> object:
            raise RuntimeError("tp/sl failed")

    class FakeConfig:
        build_version = "test"

    setting = SettingConfig(
        **{
            **_setting("buy").__dict__,
            "kill_switch_dd_pct": None,
            "kill_switch_reference_balance_jpy": None,
            "min_maintenance_margin_pct": None,
        }
    )
    aws = FakeAws()

    try:
        _create_entry_trade(
            aws_runtime=aws,  # type: ignore[arg-type]
            config=FakeConfig(),  # type: ignore[arg-type]
            oanda_client=FakeOanda(),  # type: ignore[arg-type]
            setting=setting,
            now_utc=datetime(2026, 4, 12, tzinfo=timezone.utc),
            price_snapshot=_snapshot(),
        )
    except RuntimeError as exc:
        assert str(exc) == "tp/sl failed"
    else:
        raise AssertionError("expected tp/sl failure")

    trade_statuses = [item["status"] for item in aws.trade_updates if "status" in item]
    execution_statuses = [item["status"] for item in aws.execution_updates if "status" in item]

    assert "entered" in trade_statuses
    assert "entry_failed" not in trade_statuses
    assert execution_statuses[-3:] == ["order_created", "tp_sl_requested", "tp_sl_failed"]
    assert aws.decisions[-1]["decision"] == "tp_sl_failed"
