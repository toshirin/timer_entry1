from __future__ import annotations

from datetime import datetime, timedelta
import math
from typing import Any
from zoneinfo import ZoneInfo

from .constants import PIP_SIZE
from .models import Candle, FilterDecision, SettingConfig


def _candle_map(candles: list[Candle], tz_name: str) -> dict[datetime, Candle]:
    local_map: dict[datetime, Candle] = {}
    zone = ZoneInfo(tz_name)
    for candle in candles:
        local_dt = candle.time_utc.astimezone(zone).replace(second=0, microsecond=0)
        local_map[local_dt] = candle
    return local_map


def _entry_local_dt(now_utc: datetime, setting: SettingConfig) -> datetime:
    local_now = now_utc.astimezone(ZoneInfo(setting.market_tz))
    hour, minute = [int(part) for part in setting.entry_clock_local.split(":")]
    return local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _get_candle_at(local_map: dict[datetime, Candle], base_dt: datetime, minutes_before: int) -> Candle:
    return local_map[base_dt - timedelta(minutes=minutes_before)]


def _window(
    local_map: dict[datetime, Candle],
    base_dt: datetime,
    start_before: int,
    end_before: int,
) -> list[Candle]:
    if start_before < end_before:
        start_before, end_before = end_before, start_before
    return [_get_candle_at(local_map, base_dt, minutes_before) for minutes_before in range(start_before, end_before - 1, -1)]


def _compare(operator: str, left: float, right: float) -> bool:
    if operator == "ge":
        return left >= right
    if operator == "gt":
        return left > right
    if operator == "le":
        return left <= right
    if operator == "lt":
        return left < right
    if operator == "eq":
        return left == right
    raise ValueError(f"Unsupported operator: {operator}")


def _pre_open_slope(spec: dict[str, Any], local_map: dict[datetime, Candle], entry_dt: datetime) -> FilterDecision:
    start_min = int(spec["lookback_start_min"])
    end_min = int(spec["lookback_end_min"])
    start_candle = _get_candle_at(local_map, entry_dt, start_min)
    end_candle = _get_candle_at(local_map, entry_dt, end_min)
    slope = (end_candle.bid_close - start_candle.bid_open) / PIP_SIZE
    operator = str(spec.get("operator", "ge"))
    threshold = float(spec.get("threshold", 0.0))
    return FilterDecision(
        filter_type="pre_open_slope",
        passed=_compare(operator, slope, threshold),
        values={"slope_pips": slope, "operator": operator, "threshold": threshold, "start_min": start_min, "end_min": end_min},
    )


def _shape_balance(spec: dict[str, Any], local_map: dict[datetime, Candle], entry_dt: datetime) -> FilterDecision:
    left_start = int(spec.get("left_start_min", 55))
    left_end = int(spec.get("left_end_min", 30))
    right_start = int(spec.get("right_start_min", 30))
    right_end = int(spec.get("right_end_min", 5))
    left_ret = _get_candle_at(local_map, entry_dt, left_end).bid_close - _get_candle_at(local_map, entry_dt, left_start).bid_open
    right_ret = _get_candle_at(local_map, entry_dt, right_end).bid_close - _get_candle_at(local_map, entry_dt, right_start).bid_open
    mode = str(spec.get("mode", "same_sign"))
    if mode == "left_stronger":
        passed = abs(left_ret) > abs(right_ret)
    elif mode == "right_stronger":
        passed = abs(right_ret) > abs(left_ret)
    elif mode == "same_sign":
        passed = left_ret == 0 or right_ret == 0 or (left_ret > 0) == (right_ret > 0)
    elif mode == "opposite_sign":
        passed = left_ret != 0 and right_ret != 0 and (left_ret > 0) != (right_ret > 0)
    elif mode == "right_strength_balance":
        operator = str(spec.get("operator", "ge"))
        threshold = float(spec.get("threshold", 0.0))
        balance = (abs(right_ret) - abs(left_ret)) / PIP_SIZE
        return FilterDecision(
            filter_type="shape_balance",
            passed=_compare(operator, balance, threshold),
            values={"right_strength_balance_pips": balance, "operator": operator, "threshold": threshold, "mode": mode},
        )
    elif mode == "opposite_sign_right_strength_balance":
        operator = str(spec.get("operator", "ge"))
        threshold = float(spec.get("threshold", 0.0))
        opposite = left_ret != 0 and right_ret != 0 and (left_ret > 0) != (right_ret > 0)
        balance = (abs(right_ret) - abs(left_ret)) / PIP_SIZE
        return FilterDecision(
            filter_type="shape_balance",
            passed=opposite and _compare(operator, balance, threshold),
            values={
                "left_ret_pips": left_ret / PIP_SIZE,
                "right_ret_pips": right_ret / PIP_SIZE,
                "right_strength_balance_pips": balance,
                "opposite_sign": opposite,
                "operator": operator,
                "threshold": threshold,
                "mode": mode,
            },
        )
    else:
        raise ValueError(f"Unsupported shape_balance mode: {mode}")
    return FilterDecision(
        filter_type="shape_balance",
        passed=passed,
        values={"left_ret_pips": left_ret / PIP_SIZE, "right_ret_pips": right_ret / PIP_SIZE, "mode": mode},
    )


def _pre_range_regime(spec: dict[str, Any], local_map: dict[datetime, Candle], entry_dt: datetime) -> FilterDecision:
    start_min = int(spec["lookback_start_min"])
    end_min = int(spec["lookback_end_min"])
    candles = _window(local_map, entry_dt, start_min, end_min)
    range_pips = (max(c.bid_high for c in candles) - min(c.bid_low for c in candles)) / PIP_SIZE
    operator = str(spec.get("operator", "ge"))
    threshold = float(spec.get("threshold", spec.get("aux_param", 0.0)))
    return FilterDecision(
        filter_type="pre_range_regime",
        passed=_compare(operator, range_pips, threshold),
        values={"pre_range_pips": range_pips, "operator": operator, "threshold": threshold, "start_min": start_min, "end_min": end_min},
    )


def _trend_ratio(spec: dict[str, Any], local_map: dict[datetime, Candle], entry_dt: datetime) -> FilterDecision:
    start_min = int(spec["lookback_start_min"])
    end_min = int(spec["lookback_end_min"])
    start_candle = _get_candle_at(local_map, entry_dt, start_min)
    end_candle = _get_candle_at(local_map, entry_dt, end_min)
    candles = _window(local_map, entry_dt, start_min, end_min)
    net_move = abs(end_candle.bid_close - start_candle.bid_open) / PIP_SIZE
    path_range = (max(c.bid_high for c in candles) - min(c.bid_low for c in candles)) / PIP_SIZE
    ratio = net_move / path_range if path_range > 0 else math.nan
    operator = str(spec.get("operator", "ge"))
    threshold = float(spec.get("threshold", 0.5))
    return FilterDecision(
        filter_type="trend_ratio",
        passed=path_range > 0 and _compare(operator, ratio, threshold),
        values={"trend_ratio": ratio, "net_move_pips": net_move, "path_range_pips": path_range, "operator": operator, "threshold": threshold},
    )


def evaluate_filters(*, setting: SettingConfig, now_utc: datetime, candles: list[Candle]) -> list[FilterDecision]:
    specs = setting.parsed_filter_specs()
    if not specs:
        return []

    local_map = _candle_map(candles, setting.market_tz)
    entry_dt = _entry_local_dt(now_utc, setting)
    decisions: list[FilterDecision] = []
    for spec in specs:
        filter_type = str(spec["filter_type"])
        if filter_type == "pre_open_slope":
            decisions.append(_pre_open_slope(spec, local_map, entry_dt))
        elif filter_type == "shape_balance":
            decisions.append(_shape_balance(spec, local_map, entry_dt))
        elif filter_type == "pre_range_regime":
            decisions.append(_pre_range_regime(spec, local_map, entry_dt))
        elif filter_type == "trend_ratio":
            decisions.append(_trend_ratio(spec, local_map, entry_dt))
        else:
            raise ValueError(f"Unsupported filter_type: {filter_type}")
    return decisions
