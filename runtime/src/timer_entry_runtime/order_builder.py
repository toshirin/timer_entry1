from __future__ import annotations

from dataclasses import dataclass

from timer_entry.direction import DirectionSpec, get_direction_spec

from .constants import JPY_PAIR_DECIMALS, PIP_SIZE, TRIGGER_CONDITION_ASK, TRIGGER_CONDITION_BID
from .models import PriceSnapshot, SettingConfig


@dataclass(frozen=True)
class RequestedEntry:
    price: float
    price_side: str


@dataclass(frozen=True)
class ProtectionLevels:
    tp_trigger_price: float
    tp_trigger_side: str
    sl_trigger_price: float
    sl_trigger_side: str
    tp_trigger_condition: str
    sl_trigger_condition: str


def direction_spec_for_setting(setting: SettingConfig) -> DirectionSpec:
    return get_direction_spec(setting.side)


def requested_entry_from_snapshot(setting: SettingConfig, snapshot: PriceSnapshot) -> RequestedEntry:
    spec = direction_spec_for_setting(setting)
    price = snapshot.ask if spec.entry_price_side == "ask" else snapshot.bid
    return RequestedEntry(price=price, price_side=spec.entry_price_side)


def _trigger_condition(price_side: str) -> str:
    if price_side == "bid":
        return TRIGGER_CONDITION_BID
    if price_side == "ask":
        return TRIGGER_CONDITION_ASK
    raise ValueError(f"Unsupported price side: {price_side}")


def protection_levels(setting: SettingConfig, *, entry_fill_price: float) -> ProtectionLevels:
    spec = direction_spec_for_setting(setting)
    tp_price = entry_fill_price + spec.tp_sign * setting.tp_pips * PIP_SIZE
    sl_price = entry_fill_price + spec.sl_sign * setting.sl_pips * PIP_SIZE

    tp_side = "bid" if spec.tp_hit_col.startswith("Bid_") else "ask"
    sl_side = "bid" if spec.sl_hit_col.startswith("Bid_") else "ask"
    return ProtectionLevels(
        tp_trigger_price=tp_price,
        tp_trigger_side=tp_side,
        sl_trigger_price=sl_price,
        sl_trigger_side=sl_side,
        tp_trigger_condition=_trigger_condition(tp_side),
        sl_trigger_condition=_trigger_condition(sl_side),
    )


def market_order_body(
    *,
    setting: SettingConfig,
    units: int,
    client_id: str,
    client_tag: str,
    client_comment: str,
) -> dict[str, object]:
    signed_units = units if setting.side == "buy" else -units
    return {
        "order": {
            "type": "MARKET",
            "instrument": setting.instrument,
            "units": str(signed_units),
            "timeInForce": "FOK",
            "positionFill": "DEFAULT",
            "clientExtensions": {
                "id": client_id,
                "tag": client_tag,
                "comment": client_comment,
            },
            "tradeClientExtensions": {
                "id": client_id,
                "tag": client_tag,
                "comment": client_comment,
            },
        },
    }


def trade_protection_order_body(setting: SettingConfig, *, entry_fill_price: float) -> dict[str, object]:
    levels = protection_levels(setting, entry_fill_price=entry_fill_price)
    return {
        "takeProfit": {
            "timeInForce": "GTC",
            "price": f"{levels.tp_trigger_price:.{JPY_PAIR_DECIMALS}f}",
            "triggerCondition": levels.tp_trigger_condition,
        },
        "stopLoss": {
            "timeInForce": "GTC",
            "price": f"{levels.sl_trigger_price:.{JPY_PAIR_DECIMALS}f}",
            "triggerCondition": levels.sl_trigger_condition,
        },
    }
