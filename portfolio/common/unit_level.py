from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .capital import compute_units_for_level, pnl_jpy
from .runtime_policy import LEVEL0_FIXED_UNITS, UNIT_BASIS_MONTH_END, decide_monthly_level, threshold_jpy_for_units as runtime_threshold_jpy_for_units


@dataclass
class LevelState:
    level: int


def threshold_jpy_for_units(units: int) -> float:
    return runtime_threshold_jpy_for_units(int(units))


def decide_level(current_level: int, current_units: int, cum_jpy_month: float, *, is_watch: bool) -> tuple[int, str, str]:
    decision = decide_monthly_level(
        current_level=current_level,
        current_units=current_units,
        cum_jpy_month=cum_jpy_month,
        labels=("watch",) if is_watch else (),
        unit_basis=UNIT_BASIS_MONTH_END,
    )
    return decision.next_level, decision.decision, decision.decision_reason


def simulate_level_basis(
    ledger: pd.DataFrame,
    *,
    settings: pd.DataFrame,
    initial_capital_jpy: float,
    basis: str,
    sizing_mode: str,
    equity_basis_cap_jpy: float | None,
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Monthly level simulation for one basis."""
    setting_ids = settings["setting_id"].tolist()
    levels = {row["setting_id"]: LevelState(level=int(row.get("initial_level", 0))) for _, row in settings.iterrows()}
    is_watch = {row["setting_id"]: bool(row.get("is_watch", False)) for _, row in settings.iterrows()}
    margin_targets = {row["setting_id"]: row.get("margin_ratio_target") for _, row in settings.iterrows()}
    slots = {row["setting_id"]: row.get("slot_id") for _, row in settings.iterrows()}
    sides = {row["setting_id"]: row.get("side") for _, row in settings.iterrows()}
    initial_level_sources = {row["setting_id"]: row.get("initial_level_source", "runtime_config") for _, row in settings.iterrows()}
    last_units = {row["setting_id"]: LEVEL0_FIXED_UNITS for _, row in settings.iterrows()}

    trades = ledger.copy()
    if trades.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    trades = trades.sort_values(["entry_ts_utc", "trigger_bucket_entry", "setting_id"]).reset_index(drop=True)
    trades["decision_month"] = pd.to_datetime(trades["exit_ts_local"], format="mixed").dt.to_period("M").astype(str)

    equity = float(initial_capital_jpy)
    trade_rows: list[dict[str, object]] = []
    equity_rows = [
        {
            "timestamp": date_from,
            "equity_jpy": equity,
            "basis": basis,
            "sizing_mode": sizing_mode,
            "equity_basis_cap_jpy": equity_basis_cap_jpy,
            "event_type": "initial",
        }
    ]
    monthly_rows: list[dict[str, object]] = []
    level_rows: list[dict[str, object]] = []
    months = pd.period_range(date_from, date_to, freq="M").astype(str)

    for month in months:
        month_trades = trades.loc[trades["decision_month"] == month].copy()
        pnl_by_setting = {setting_id: 0.0 for setting_id in setting_ids}
        units_by_setting: dict[str, int] = {}

        for _, trade in month_trades.iterrows():
            sid = str(trade["setting_id"])
            level = levels[sid].level
            sizing_equity = min(equity, float(equity_basis_cap_jpy)) if equity_basis_cap_jpy is not None else equity
            units = compute_units_for_level(
                equity_jpy=sizing_equity,
                entry_price=float(trade["entry_price"]),
                margin_ratio_target=float(margin_targets[sid]) if pd.notna(margin_targets[sid]) else None,
                level=level,
            )
            raw_units = units
            units_by_setting[sid] = units
            last_units[sid] = units
            trade_pnl = pnl_jpy(units=units, pnl_pips=float(trade["pnl_pips"]))
            equity += trade_pnl
            pnl_by_setting[sid] += trade_pnl
            row = trade.to_dict()
            row.update(
                {
                    "basis": basis,
                    "sizing_mode": sizing_mode,
                    "equity_basis_cap_jpy": equity_basis_cap_jpy,
                    "sizing_equity_jpy": sizing_equity,
                    "unit_level": level,
                    "raw_units": raw_units,
                    "units": units,
                    "notional_jpy": units * float(trade["entry_price"]),
                    "pnl_jpy": trade_pnl,
                    "equity_jpy": equity,
                }
            )
            trade_rows.append(row)
            equity_rows.append(
                {
                    "timestamp": trade["exit_ts"],
                    "equity_jpy": equity,
                    "basis": basis,
                    "sizing_mode": sizing_mode,
                    "equity_basis_cap_jpy": equity_basis_cap_jpy,
                    "event_type": "exit",
                    "setting_id": sid,
                    "pnl_jpy": trade_pnl,
                }
            )

        for sid in setting_ids:
            current_level = levels[sid].level
            current_units = units_by_setting.get(sid, last_units[sid])
            cum = float(pnl_by_setting[sid])
            next_level, decision, reason = decide_level(current_level, current_units, cum, is_watch=is_watch[sid])
            threshold = threshold_jpy_for_units(current_units)
            level_rows.append(
                {
                    "basis": basis,
                    "sizing_mode": sizing_mode,
                    "equity_basis_cap_jpy": equity_basis_cap_jpy,
                    "decision_month": month,
                    "setting_id": sid,
                    "slot_id": slots[sid],
                    "side": sides[sid],
                    "current_level": current_level,
                    "next_level": next_level,
                    "initial_level_source": initial_level_sources[sid],
                    "decision": decision,
                    "decision_reason": reason,
                    "current_units": current_units,
                    "threshold_jpy": threshold,
                    "cum_jpy_month": cum,
                    "unit_basis": "month_end_latest_equity_runtime_compute_units",
                }
            )
            monthly_rows.append(
                {
                    "basis": basis,
                    "sizing_mode": sizing_mode,
                    "equity_basis_cap_jpy": equity_basis_cap_jpy,
                    "decision_month": month,
                    "setting_id": sid,
                    "cum_jpy_month": cum,
                }
            )
            levels[sid].level = next_level

    return pd.DataFrame(trade_rows), pd.DataFrame(monthly_rows), pd.DataFrame(level_rows)


def level_pivot(level_history: pd.DataFrame) -> pd.DataFrame:
    if level_history.empty:
        return pd.DataFrame()
    return (
        level_history.pivot_table(
            index=["basis", "sizing_mode", "decision_month"],
            columns="setting_id",
            values="next_level",
            aggfunc="last",
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )
