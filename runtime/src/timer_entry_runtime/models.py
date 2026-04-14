from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import json
from typing import Any

from .constants import PIP_SIZE
from .time_utils import parse_oanda_time


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value != "":
        return float(value)
    return None


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _to_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


@dataclass(frozen=True)
class HandlerResult:
    status: str
    message: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "message": self.message, "details": self.details}


@dataclass(frozen=True)
class TriggerContext:
    handler_name: str
    requested_trigger_bucket: str | None
    invoked_at_utc: str


@dataclass(frozen=True)
class SettingConfig:
    setting_id: str
    enabled: bool
    strategy_id: str
    slot_id: str
    market_session: str
    market_tz: str
    instrument: str
    side: str
    entry_clock_local: str
    forced_exit_clock_local: str
    trigger_bucket_entry: str
    trigger_bucket_exit: str
    fixed_units: int | None
    margin_ratio_target: float | None
    size_scale_pct: float | None
    tp_pips: float
    sl_pips: float
    research_label: str | None
    labels: list[str]
    market_open_check_seconds: int
    max_concurrent_positions: int | None
    kill_switch_dd_pct: float | None
    kill_switch_reference_balance_jpy: float | None
    min_maintenance_margin_pct: float | None
    filter_spec_json: str | None
    execution_spec_json: str | None
    notes: str | None

    @classmethod
    def from_item(cls, item: dict[str, Any]) -> "SettingConfig":
        return cls(
            setting_id=str(item["setting_id"]),
            enabled=bool(item.get("enabled", False)),
            strategy_id=str(item.get("strategy_id", "")),
            slot_id=str(item.get("slot_id", "")),
            market_session=str(item.get("market_session", "")),
            market_tz=str(item["market_tz"]),
            instrument=str(item.get("instrument", "USD_JPY")),
            side=str(item.get("side", "buy")).lower(),
            entry_clock_local=str(item["entry_clock_local"]),
            forced_exit_clock_local=str(item["forced_exit_clock_local"]),
            trigger_bucket_entry=str(item["trigger_bucket_entry"]),
            trigger_bucket_exit=str(item["trigger_bucket_exit"]),
            fixed_units=int(item["fixed_units"]) if item.get("fixed_units") is not None else None,
            margin_ratio_target=_to_float(item.get("margin_ratio_target")),
            size_scale_pct=_to_float(item.get("size_scale_pct")),
            tp_pips=float(item.get("tp_pips", 0)),
            sl_pips=float(item.get("sl_pips", 0)),
            research_label=_to_str(item.get("research_label")),
            labels=_to_str_list(item.get("labels")),
            market_open_check_seconds=int(item.get("market_open_check_seconds", 10)),
            max_concurrent_positions=(
                int(item["max_concurrent_positions"])
                if item.get("max_concurrent_positions") is not None
                else 1
            ),
            kill_switch_dd_pct=_to_float(item.get("kill_switch_dd_pct")),
            kill_switch_reference_balance_jpy=_to_float(item.get("kill_switch_reference_balance_jpy")),
            min_maintenance_margin_pct=_to_float(item.get("min_maintenance_margin_pct")),
            filter_spec_json=_to_str(item.get("filter_spec_json")),
            execution_spec_json=_to_str(item.get("execution_spec_json")),
            notes=_to_str(item.get("notes")),
        )

    def parsed_filter_specs(self) -> list[dict[str, Any]]:
        if not self.filter_spec_json:
            return []
        loaded = json.loads(self.filter_spec_json)
        if isinstance(loaded, list):
            return [item for item in loaded if isinstance(item, dict)]
        if isinstance(loaded, dict):
            return [loaded]
        raise ValueError("filter_spec_json must be a JSON object or array")


@dataclass(frozen=True)
class OandaSecret:
    access_token: str
    account_id: str
    environment: str


@dataclass(frozen=True)
class PriceSnapshot:
    instrument: str
    bid: float
    ask: float
    time_utc: datetime


@dataclass(frozen=True)
class AccountSnapshot:
    account_id: str
    balance: float


@dataclass(frozen=True)
class Candle:
    time_utc: datetime
    bid_open: float
    bid_high: float
    bid_low: float
    bid_close: float
    complete: bool

    @classmethod
    def from_oanda(cls, item: dict[str, Any]) -> "Candle":
        bid = item["bid"]
        return cls(
            time_utc=parse_oanda_time(item["time"]),
            bid_open=float(bid["o"]),
            bid_high=float(bid["h"]),
            bid_low=float(bid["l"]),
            bid_close=float(bid["c"]),
            complete=bool(item.get("complete", False)),
        )


@dataclass(frozen=True)
class FilterDecision:
    filter_type: str
    passed: bool
    values: dict[str, Any]


@dataclass(frozen=True)
class OrderResult:
    order_id: str | None
    trade_id: str | None
    fill_price: float | None
    client_id: str | None
    raw_response: dict[str, Any]


@dataclass(frozen=True)
class ProtectionOrderResult:
    take_profit_order_id: str | None
    stop_loss_order_id: str | None
    raw_response: dict[str, Any]


@dataclass(frozen=True)
class CloseResult:
    order_id: str | None
    fill_price: float | None
    raw_response: dict[str, Any]


@dataclass(frozen=True)
class TradeComputation:
    requested_units: int
    sizing_basis: str
    effective_margin_ratio: float | None
    estimated_margin_ratio_after_entry: float | None
    margin_price: float
    margin_price_side: str


def pnl_pips(entry_price: float, exit_price: float, side: str) -> float:
    diff = exit_price - entry_price
    return diff / PIP_SIZE if side == "buy" else -diff / PIP_SIZE
