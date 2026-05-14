from __future__ import annotations

import pandas as pd

from .capital import compute_units, pnl_jpy


def simulate_conflict_100pct(
    ledger: pd.DataFrame,
    *,
    initial_capital_jpy: float,
    equity_basis_cap_jpy: float | None = None,
    basis: str = "unlimited",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Simulate account-wide one-open-position conflict with 100% size scale."""
    if ledger.empty:
        empty = ledger.copy()
        return empty, pd.DataFrame(), pd.DataFrame()

    rows: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    equity_rows: list[dict[str, object]] = []
    equity = float(initial_capital_jpy)
    active: dict[str, object] | None = None

    sorted_ledger = ledger.sort_values(["entry_ts_utc", "trigger_bucket_entry", "setting_id"]).reset_index(drop=True)
    start_ts = pd.to_datetime(sorted_ledger["entry_ts"].min())
    equity_rows.append({"basis": basis, "timestamp": start_ts, "equity_jpy": equity, "event_type": "initial"})

    def close_active(until_ts: pd.Timestamp | None = None) -> None:
        nonlocal active, equity
        if active is None:
            return
        equity += float(active["pnl_jpy"])
        equity_rows.append(
            {
                "timestamp": active["exit_ts"],
                "basis": basis,
                "equity_jpy": equity,
                "event_type": "exit",
                "setting_id": active["setting_id"],
                "pnl_jpy": active["pnl_jpy"],
            }
        )
        active = None

    for _, trade in sorted_ledger.iterrows():
        entry_ts = pd.to_datetime(trade["entry_ts"])
        if active is not None and entry_ts >= pd.to_datetime(active["exit_ts"]):
            close_active(entry_ts)

        margin_target = float(trade["margin_ratio_target"]) if pd.notna(trade["margin_ratio_target"]) else None
        sizing_equity = min(equity, float(equity_basis_cap_jpy)) if equity_basis_cap_jpy is not None else equity
        units = compute_units(
            equity_jpy=sizing_equity,
            entry_price=float(trade["entry_price"]),
            margin_ratio_target=margin_target,
            size_scale_pct=100.0,
        )
        raw_units = units
        trade_pnl_jpy = pnl_jpy(units=units, pnl_pips=float(trade["pnl_pips"]))
        row = trade.to_dict()
        row.update(
            {
                "basis": basis,
                "sizing_equity_jpy": sizing_equity,
                "equity_basis_cap_jpy": equity_basis_cap_jpy,
                "raw_units": raw_units,
                "units": units,
                "notional_jpy": units * float(trade["entry_price"]),
                "pnl_jpy": trade_pnl_jpy,
                "equity_before_jpy": equity,
                "executed": active is None,
                "blocked": active is not None,
                "blocker_setting_id": active["setting_id"] if active is not None else None,
            }
        )

        if active is None:
            active = row.copy()
        else:
            blocker = active
            events.append(
                {
                    "blocked_setting_id": trade["setting_id"],
                    "blocker_setting_id": blocker["setting_id"],
                    "blocked_entry_time": trade["entry_time"],
                    "blocked_exit_time": trade["exit_time"],
                    "blocker_entry_time": blocker["entry_time"],
                    "blocker_exit_time": blocker["exit_time"],
                    "blocked_pnl_pips": float(trade["pnl_pips"]),
                    "blocked_units": units,
                    "blocked_pnl_jpy": trade_pnl_jpy,
                    "blocker_pnl_pips": float(blocker["pnl_pips"]),
                    "blocker_units": int(blocker["units"]),
                    "blocker_pnl_jpy": float(blocker["pnl_jpy"]),
                    "opportunity_delta_jpy": trade_pnl_jpy - float(blocker["pnl_jpy"]),
                }
            )
        rows.append(row)

    close_active()
    result = pd.DataFrame(rows)
    equity_df = pd.DataFrame(equity_rows).sort_values("timestamp").reset_index(drop=True)
    return result, pd.DataFrame(events), equity_df


def conflict_blocker_summary(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(
            columns=[
                "blocker_setting_id",
                "blocked_setting_id",
                "block_count",
                "blocked_pnl_jpy_sum",
                "blocked_positive_pnl_jpy_sum",
                "blocked_negative_pnl_jpy_sum",
                "blocker_pnl_jpy_sum",
                "blocker_positive_pnl_jpy_sum",
                "blocker_negative_pnl_jpy_sum",
                "opportunity_delta_jpy_sum",
            ]
        )
    rows: list[dict[str, object]] = []
    for (blocker, blocked), group in events.groupby(["blocker_setting_id", "blocked_setting_id"], dropna=False):
        blocked_pnl = pd.to_numeric(group["blocked_pnl_jpy"], errors="coerce").fillna(0.0)
        blocker_pnl = pd.to_numeric(group["blocker_pnl_jpy"], errors="coerce").fillna(0.0)
        rows.append(
            {
                "blocker_setting_id": blocker,
                "blocked_setting_id": blocked,
                "block_count": int(len(group)),
                "blocked_pnl_jpy_sum": float(blocked_pnl.sum()),
                "blocked_positive_pnl_jpy_sum": float(blocked_pnl[blocked_pnl > 0].sum()),
                "blocked_negative_pnl_jpy_sum": float(blocked_pnl[blocked_pnl < 0].sum()),
                "blocker_pnl_jpy_sum": float(blocker_pnl.sum()),
                "blocker_positive_pnl_jpy_sum": float(blocker_pnl[blocker_pnl > 0].sum()),
                "blocker_negative_pnl_jpy_sum": float(blocker_pnl[blocker_pnl < 0].sum()),
                "opportunity_delta_jpy_sum": float(pd.to_numeric(group["opportunity_delta_jpy"], errors="coerce").sum()),
            }
        )
    return pd.DataFrame(rows).sort_values(["opportunity_delta_jpy_sum", "block_count"], ascending=[True, False])
