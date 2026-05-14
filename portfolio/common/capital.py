from __future__ import annotations

import math
from typing import Any

import pandas as pd


OANDA_MARGIN_RATE = 0.04
PIP_VALUE_JPY_PER_UNIT = 0.01

LEVEL_SIZE_SCALE_PCT: dict[int, float | None] = {
    0: None,
    1: 0.1,
    2: 0.3,
    3: 1.0,
    4: 3.0,
    5: 10.0,
    6: 30.0,
    7: 100.0,
}
LEVEL0_FIXED_UNITS = 10


def compute_units(
    *,
    equity_jpy: float,
    entry_price: float,
    margin_ratio_target: float | None,
    size_scale_pct: float | None,
    fixed_units: int | None = None,
) -> int:
    if fixed_units is not None:
        return int(fixed_units)
    if margin_ratio_target is None or margin_ratio_target <= 0:
        raise ValueError("margin_ratio_target is required for portfolio sizing")
    if entry_price <= 0:
        raise ValueError("entry_price must be positive")
    scale = 100.0 if size_scale_pct is None else float(size_scale_pct)
    if scale <= 0:
        raise ValueError("size_scale_pct must be positive")
    effective_margin_ratio = float(margin_ratio_target) * (100.0 / scale)
    units = int(float(equity_jpy) / (effective_margin_ratio / 100.0) / (float(entry_price) * OANDA_MARGIN_RATE))
    return max(0, units)


def compute_units_for_level(
    *,
    equity_jpy: float,
    entry_price: float,
    margin_ratio_target: float | None,
    level: int,
) -> int:
    if level == 0:
        return LEVEL0_FIXED_UNITS
    return compute_units(
        equity_jpy=equity_jpy,
        entry_price=entry_price,
        margin_ratio_target=margin_ratio_target,
        size_scale_pct=LEVEL_SIZE_SCALE_PCT[level],
    )


def pnl_jpy(*, units: int | float, pnl_pips: int | float) -> float:
    return float(units) * float(pnl_pips) * PIP_VALUE_JPY_PER_UNIT


def max_drawdown_pct(equity: pd.Series) -> float:
    values = pd.to_numeric(equity, errors="coerce").dropna()
    if values.empty:
        return 0.0
    peak = values.cummax()
    dd = values / peak - 1.0
    return float(dd.min())


def cagr(*, initial_capital_jpy: float, final_equity_jpy: float, start: pd.Timestamp, end: pd.Timestamp) -> float:
    if initial_capital_jpy <= 0 or final_equity_jpy <= 0:
        return -1.0
    days = max(1, int((end.normalize() - start.normalize()).days) + 1)
    years = days / 365.25
    return float((final_equity_jpy / initial_capital_jpy) ** (1.0 / years) - 1.0)


def signed_sums(values: pd.Series) -> dict[str, float]:
    v = pd.to_numeric(values, errors="coerce").fillna(0.0)
    return {
        "sum": float(v.sum()),
        "positive_sum": float(v[v > 0.0].sum()),
        "negative_sum": float(v[v < 0.0].sum()),
    }


def write_jsonable_float(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value

