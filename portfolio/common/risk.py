from __future__ import annotations

import math

import pandas as pd


def profit_factor(values: pd.Series) -> float:
    pnl = pd.to_numeric(values, errors="coerce").dropna()
    if pnl.empty:
        return math.nan
    gains = float(pnl[pnl > 0.0].sum())
    losses = float(-pnl[pnl < 0.0].sum())
    if losses == 0.0:
        return math.inf if gains > 0.0 else math.nan
    return gains / losses


def max_drawdown_jpy_from_equity(equity: pd.Series) -> float:
    values = pd.to_numeric(equity, errors="coerce").dropna()
    if values.empty:
        return 0.0
    dd = values - values.cummax()
    return float(dd.min())


def max_drawdown_jpy_from_pnl(values: pd.Series) -> float:
    pnl = pd.to_numeric(values, errors="coerce").dropna()
    if pnl.empty:
        return 0.0
    curve = pnl.cumsum()
    dd = curve - curve.cummax()
    return float(dd.min())


def max_consecutive_losses(values: pd.Series) -> int:
    pnl = pd.to_numeric(values, errors="coerce").dropna()
    worst = 0
    current = 0
    for value in pnl:
        if value < 0.0:
            current += 1
            worst = max(worst, current)
        else:
            current = 0
    return worst


def trade_risk_metrics(values: pd.Series) -> dict[str, float | int]:
    pnl = pd.to_numeric(values, errors="coerce").dropna()
    if pnl.empty:
        return {
            "trade_count": 0,
            "win_rate": math.nan,
            "profit_factor": math.nan,
            "avg_pnl_jpy": math.nan,
            "median_pnl_jpy": math.nan,
            "best_trade_pnl_jpy": math.nan,
            "worst_trade_pnl_jpy": math.nan,
            "max_consecutive_losses": 0,
            "trade_pnl_max_dd_jpy": 0.0,
        }
    return {
        "trade_count": int(len(pnl)),
        "win_rate": float((pnl > 0.0).mean()),
        "profit_factor": profit_factor(pnl),
        "avg_pnl_jpy": float(pnl.mean()),
        "median_pnl_jpy": float(pnl.median()),
        "best_trade_pnl_jpy": float(pnl.max()),
        "worst_trade_pnl_jpy": float(pnl.min()),
        "max_consecutive_losses": max_consecutive_losses(pnl),
        "trade_pnl_max_dd_jpy": max_drawdown_jpy_from_pnl(pnl),
    }

