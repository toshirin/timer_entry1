from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from portfolio.common.capital import cagr, compute_units_for_level, max_drawdown_pct, pnl_jpy
from portfolio.common.initial_levels import add_initial_level_args, apply_initial_levels
from portfolio.common.inputs import load_settings
from portfolio.common.ledger import build_trade_ledger
from portfolio.common.reporting import concat_frames, ensure_out_dir, git_commit, write_csv, write_json
from portfolio.common.tax import ExternalLossOffset, month_day_date, parse_external_loss_offsets
from portfolio.common.unit_level import LEVEL0_FIXED_UNITS, decide_level, threshold_jpy_for_units


@dataclass
class LossState:
    internal_loss_carryover_jpy: float
    external_offsets: list[ExternalLossOffset]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run portfolio E013 reinvest/tax/takehome simulation.")
    parser.add_argument("--runtime-config-dir", default="runtime/config")
    parser.add_argument("--qualify-out-dir", default="qualify/out")
    parser.add_argument("--out-dir", default="portfolio/out/E013/latest")
    parser.add_argument("--date-from", default="2019-01-01")
    parser.add_argument("--date-to", default="2025-12-31")
    parser.add_argument("--initial-capital-jpy", type=float, required=True)
    parser.add_argument("--include-disabled", action="store_true")
    add_initial_level_args(parser)
    parser.add_argument("--reinvest-ratio", type=float, default=0.5)
    parser.add_argument("--tax-ratio", type=float, default=0.2)
    parser.add_argument("--takehome-ratio", type=float, default=0.3)
    parser.add_argument("--tax-withdraw-month-day", default="02-01")
    parser.add_argument("--takehome-withdraw-month-day", default="02-01")
    parser.add_argument("--external-loss-offset-json", default=None)
    return parser.parse_args()


def _withdraw_ts(value: date) -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(value, time(23, 59, 59)))


def _allocate_year(
    *,
    tax_year: int,
    yearly_realized_pnl_jpy: float,
    loss_state: LossState,
    reinvest_ratio: float,
    tax_ratio: float,
    takehome_ratio: float,
    tax_withdraw_date: date,
    takehome_withdraw_date: date,
    forced_final_settlement: bool,
) -> dict[str, object]:
    internal_before = loss_state.internal_loss_carryover_jpy
    external_used = 0.0
    taxable_base = float(yearly_realized_pnl_jpy)
    if taxable_base < 0:
        loss_state.internal_loss_carryover_jpy += -taxable_base
        taxable = 0.0
    else:
        internal_used = min(loss_state.internal_loss_carryover_jpy, taxable_base)
        taxable_base -= internal_used
        loss_state.internal_loss_carryover_jpy -= internal_used
        for offset in loss_state.external_offsets:
            if taxable_base <= 0:
                break
            if offset.amount_jpy <= 0:
                continue
            if offset.expires_on is not None and offset.expires_on < date(tax_year, 12, 31):
                continue
            used = min(offset.amount_jpy, taxable_base)
            offset.amount_jpy -= used
            taxable_base -= used
            external_used += used
        taxable = max(0.0, taxable_base)
    return {
        "tax_year": tax_year,
        "yearly_realized_pnl_jpy": float(yearly_realized_pnl_jpy),
        "internal_loss_carryover_before_jpy": internal_before,
        "internal_loss_carryover_after_jpy": loss_state.internal_loss_carryover_jpy,
        "external_loss_offset_used_jpy": external_used,
        "taxable_profit_jpy": taxable,
        "reinvest_amount_jpy": taxable * reinvest_ratio,
        "tax_amount_jpy": taxable * tax_ratio,
        "takehome_amount_jpy": taxable * takehome_ratio,
        "tax_withdraw_date": tax_withdraw_date,
        "takehome_withdraw_date": takehome_withdraw_date,
        "forced_final_settlement": forced_final_settlement,
    }


def _simulate_mode(
    ledger: pd.DataFrame,
    *,
    settings: pd.DataFrame,
    mode: str,
    sizing_mode: str,
    equity_basis_cap_jpy: float | None,
    initial_capital_jpy: float,
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
    reinvest_ratio: float,
    tax_ratio: float,
    takehome_ratio: float,
    tax_withdraw_month_day: str,
    takehome_withdraw_month_day: str,
    external_loss_offsets: list[ExternalLossOffset],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    equity = float(initial_capital_jpy)
    active: dict[str, object] | None = None
    rows: list[dict[str, object]] = []
    equity_rows = [
        {
            "basis": mode,
            "sizing_mode": sizing_mode,
            "equity_basis_cap_jpy": equity_basis_cap_jpy,
            "timestamp": date_from,
            "equity_jpy": equity,
            "event_type": "initial",
        }
    ]
    allocation_rows: list[dict[str, object]] = []
    cashflow_rows: list[dict[str, object]] = []
    pending_cashflows: list[dict[str, object]] = []
    yearly_pnl: dict[int, float] = {}
    finalized_years: set[int] = set()
    setting_ids = settings["setting_id"].tolist()
    levels = {row["setting_id"]: int(row.get("initial_level", 0)) for _, row in settings.iterrows()}
    is_watch = {row["setting_id"]: bool(row.get("is_watch", False)) for _, row in settings.iterrows()}
    margin_targets = {row["setting_id"]: row.get("margin_ratio_target") for _, row in settings.iterrows()}
    slots = {row["setting_id"]: row.get("slot_id") for _, row in settings.iterrows()}
    sides = {row["setting_id"]: row.get("side") for _, row in settings.iterrows()}
    initial_level_sources = {row["setting_id"]: row.get("initial_level_source", "runtime_config") for _, row in settings.iterrows()}
    monthly_pnl_by_period: dict[str, dict[str, float]] = {}
    last_units = {setting_id: LEVEL0_FIXED_UNITS for setting_id in setting_ids}
    level_rows: list[dict[str, object]] = []
    current_period = pd.Period(date_from, freq="M")
    end_period = pd.Period(date_to, freq="M")
    loss_state = LossState(
        internal_loss_carryover_jpy=0.0,
        external_offsets=[ExternalLossOffset(item.amount_jpy, item.expires_on) for item in external_loss_offsets],
    )

    def finalize_month(period: pd.Period) -> None:
        period_key = str(period)
        period_pnl = monthly_pnl_by_period.get(period_key, {})
        for sid in setting_ids:
            current_level = levels[sid]
            current_units = last_units[sid]
            cum = float(period_pnl.get(sid, 0.0))
            next_level, decision, reason = decide_level(
                current_level,
                current_units,
                cum,
                is_watch=is_watch[sid],
            )
            level_rows.append(
                {
                    "basis": mode,
                    "sizing_mode": sizing_mode,
                    "equity_basis_cap_jpy": equity_basis_cap_jpy,
                    "decision_month": str(period),
                    "setting_id": sid,
                    "slot_id": slots[sid],
                    "side": sides[sid],
                    "current_level": current_level,
                    "next_level": next_level,
                    "initial_level_source": initial_level_sources[sid],
                    "decision": decision,
                    "decision_reason": reason,
                    "current_units": current_units,
                    "threshold_jpy": threshold_jpy_for_units(current_units),
                    "cum_jpy_month": cum,
                    "unit_basis": "month_end_latest_equity_runtime_compute_units",
                }
            )
            levels[sid] = next_level
        monthly_pnl_by_period.pop(period_key, None)

    def apply_cashflows(until_ts: pd.Timestamp) -> None:
        nonlocal equity
        due = [item for item in pending_cashflows if pd.to_datetime(item["event_ts"]) <= until_ts]
        for item in sorted(due, key=lambda x: x["event_ts"]):
            if item.get("applied"):
                continue
            amount = float(item["amount_jpy"])
            before = equity
            equity -= amount
            item["applied"] = True
            cashflow_rows.append(
                {
                    "basis": mode,
                    "sizing_mode": sizing_mode,
                    "equity_basis_cap_jpy": equity_basis_cap_jpy,
                    "event_date": pd.to_datetime(item["event_ts"]).date(),
                    "event_type": item["event_type"],
                    "tax_year": item["tax_year"],
                    "amount_jpy": amount,
                    "equity_before_jpy": before,
                    "equity_after_jpy": equity,
                    "forced_final_settlement": item["forced_final_settlement"],
                }
            )
            equity_rows.append(
                {
                    "basis": mode,
                    "sizing_mode": sizing_mode,
                    "equity_basis_cap_jpy": equity_basis_cap_jpy,
                    "timestamp": item["event_ts"],
                    "equity_jpy": equity,
                    "event_type": item["event_type"],
                    "tax_year": item["tax_year"],
                }
            )

    def finalize_year(year: int, *, forced: bool) -> None:
        if year in finalized_years:
            return
        finalized_years.add(year)
        if mode == "immediate_withdrawal" and not forced:
            tax_date = date(year, 12, 31)
            takehome_date = date(year, 12, 31)
        elif forced:
            tax_date = date_to.date()
            takehome_date = date_to.date()
        else:
            tax_date = month_day_date(year + 1, tax_withdraw_month_day)
            takehome_date = month_day_date(year + 1, takehome_withdraw_month_day)
        allocation = _allocate_year(
            tax_year=year,
            yearly_realized_pnl_jpy=yearly_pnl.get(year, 0.0),
            loss_state=loss_state,
            reinvest_ratio=reinvest_ratio,
            tax_ratio=tax_ratio,
            takehome_ratio=takehome_ratio,
            tax_withdraw_date=tax_date,
            takehome_withdraw_date=takehome_date,
            forced_final_settlement=forced,
        )
        allocation["basis"] = mode
        allocation["sizing_mode"] = sizing_mode
        allocation["equity_basis_cap_jpy"] = equity_basis_cap_jpy
        allocation_rows.append(allocation)
        for event_type, amount_key, when in (
            ("final_tax_withdrawal" if forced else "tax_withdrawal", "tax_amount_jpy", tax_date),
            ("final_takehome_withdrawal" if forced else "takehome_withdrawal", "takehome_amount_jpy", takehome_date),
        ):
            amount = float(allocation[amount_key])
            if amount <= 0:
                continue
            pending_cashflows.append(
                {
                    "event_ts": _withdraw_ts(when),
                    "event_type": event_type,
                    "tax_year": year,
                    "amount_jpy": amount,
                    "forced_final_settlement": forced,
                    "applied": False,
                }
            )

    def close_active() -> None:
        nonlocal active, equity
        if active is None:
            return
        pnl = float(active["pnl_jpy"])
        equity += pnl
        sid = str(active["setting_id"])
        exit_period = str(pd.Period(pd.to_datetime(active["exit_ts_local"], format="mixed"), freq="M"))
        if exit_period not in monthly_pnl_by_period:
            monthly_pnl_by_period[exit_period] = {setting_id: 0.0 for setting_id in setting_ids}
        monthly_pnl_by_period[exit_period][sid] += pnl
        tax_year = int(pd.to_datetime(active["exit_ts_local"], format="mixed").year)
        yearly_pnl[tax_year] = yearly_pnl.get(tax_year, 0.0) + pnl
        equity_rows.append(
            {
                "basis": mode,
                "sizing_mode": sizing_mode,
                "equity_basis_cap_jpy": equity_basis_cap_jpy,
                "timestamp": active["exit_ts"],
                "equity_jpy": equity,
                "event_type": "exit",
                "setting_id": active["setting_id"],
                "pnl_jpy": pnl,
            }
        )
        active = None

    sorted_ledger = ledger.sort_values(["entry_ts_utc", "trigger_bucket_entry", "setting_id"]).reset_index(drop=True)
    for _, trade in sorted_ledger.iterrows():
        entry_ts = pd.to_datetime(trade["entry_ts"])
        trade_period = pd.Period(pd.to_datetime(trade["date_local"], format="mixed"), freq="M")
        while current_period < trade_period:
            if active is not None and pd.Period(pd.to_datetime(active["exit_ts_local"], format="mixed"), freq="M") <= current_period:
                close_active()
            finalize_month(current_period)
            current_period += 1
        if active is not None and entry_ts >= pd.to_datetime(active["exit_ts"]):
            close_active()
        for year in range(date_from.year, entry_ts.year):
            finalize_year(year, forced=False)
        apply_cashflows(entry_ts)

        if active is not None:
            row = trade.to_dict()
            row.update(
                {
                    "basis": mode,
                    "sizing_mode": sizing_mode,
                    "equity_basis_cap_jpy": equity_basis_cap_jpy,
                    "executed": False,
                    "blocked": True,
                    "blocker_setting_id": active["setting_id"],
                }
            )
            rows.append(row)
            continue

        sid = str(trade["setting_id"])
        level = levels[sid]
        margin_target = float(margin_targets[sid]) if pd.notna(margin_targets[sid]) else None
        raw_units = compute_units_for_level(
            equity_jpy=equity,
            entry_price=float(trade["entry_price"]),
            margin_ratio_target=margin_target,
            level=level,
        )
        sizing_equity = min(equity, float(equity_basis_cap_jpy)) if equity_basis_cap_jpy is not None else equity
        units = (
            compute_units_for_level(
                equity_jpy=sizing_equity,
                entry_price=float(trade["entry_price"]),
                margin_ratio_target=margin_target,
                level=level,
            )
            if equity_basis_cap_jpy is not None
            else raw_units
        )
        last_units[sid] = units
        trade_pnl = pnl_jpy(units=units, pnl_pips=float(trade["pnl_pips"]))
        row = trade.to_dict()
        row.update(
            {
                "basis": mode,
                "sizing_mode": sizing_mode,
                "equity_basis_cap_jpy": equity_basis_cap_jpy,
                "executed": True,
                "blocked": False,
                "unit_level": level,
                "raw_units": raw_units,
                "units": units,
                "sizing_equity_jpy": sizing_equity,
                "notional_jpy": units * float(trade["entry_price"]),
                "pnl_jpy": trade_pnl,
                "equity_before_jpy": equity,
            }
        )
        active = row.copy()
        rows.append(row)

    if active is not None:
        close_active()
    while current_period <= end_period:
        finalize_month(current_period)
        current_period += 1
    for year in range(date_from.year, date_to.year):
        finalize_year(year, forced=False)
    finalize_year(date_to.year, forced=True)
    apply_cashflows(pd.Timestamp(datetime.combine(date_to.date(), time(23, 59, 59))))

    return (
        pd.DataFrame(rows),
        pd.DataFrame(allocation_rows),
        pd.DataFrame(cashflow_rows),
        pd.DataFrame(equity_rows),
        pd.DataFrame(level_rows),
    )


def _settings_frame(settings: list[object]) -> pd.DataFrame:
    rows = []
    for setting in settings:
        rows.append(
            {
                "setting_id": setting.setting_id,
                "slot_id": setting.slot_id,
                "side": setting.side,
                "is_watch": setting.is_watch,
                "margin_ratio_target": setting.effective_margin_ratio_target,
                "initial_level": setting.unit_level if setting.unit_level is not None else 0,
            }
        )
    return pd.DataFrame(rows)


def run(args: argparse.Namespace) -> dict[str, pd.DataFrame]:
    total_ratio = args.reinvest_ratio + args.tax_ratio + args.takehome_ratio
    if abs(total_ratio - 1.0) > 1e-9:
        raise ValueError("reinvest_ratio + tax_ratio + takehome_ratio must equal 1.0")

    out_dir = ensure_out_dir(args.out_dir)
    date_from = pd.to_datetime(args.date_from)
    date_to = pd.to_datetime(args.date_to)
    settings = load_settings(args.runtime_config_dir, include_disabled=args.include_disabled)
    settings_df = _settings_frame(settings)
    settings_df = apply_initial_levels(
        settings_df,
        global_initial_level=args.initial_level,
        setting_overrides=args.initial_level_setting,
    )
    ledger, input_summary = build_trade_ledger(
        settings,
        qualify_out_dir=args.qualify_out_dir,
        date_from=date_from.date(),
        date_to=date_to.date(),
    )
    if not ledger.empty:
        ledger = ledger.loc[ledger["margin_ratio_target"].notna()].copy()
    external_offsets = parse_external_loss_offsets(args.external_loss_offset_json)

    outputs = []
    for mode in ("deferred_withdrawal", "immediate_withdrawal"):
        for sizing_mode, equity_basis_cap_jpy in (("unlimited", None), ("equity_basis_cap_100m_jpy", 100_000_000.0)):
            outputs.append(
                _simulate_mode(
                    ledger,
                    settings=settings_df,
                    mode=mode,
                    sizing_mode=sizing_mode,
                    equity_basis_cap_jpy=equity_basis_cap_jpy,
                    initial_capital_jpy=float(args.initial_capital_jpy),
                    date_from=date_from,
                    date_to=date_to,
                    reinvest_ratio=float(args.reinvest_ratio),
                    tax_ratio=float(args.tax_ratio),
                    takehome_ratio=float(args.takehome_ratio),
                    tax_withdraw_month_day=args.tax_withdraw_month_day,
                    takehome_withdraw_month_day=args.takehome_withdraw_month_day,
                    external_loss_offsets=external_offsets,
                )
            )
    trade_ledger = concat_frames([item[0] for item in outputs])
    yearly = concat_frames([item[1] for item in outputs])
    cashflows = concat_frames([item[2] for item in outputs])
    equity_curve = concat_frames([item[3] for item in outputs])
    level_history = concat_frames([item[4] for item in outputs])

    summary_rows = []
    for (basis, sizing_mode), group in equity_curve.groupby(["basis", "sizing_mode"]):
        final_equity = float(group.sort_values("timestamp")["equity_jpy"].iloc[-1])
        summary_rows.append(
            {
                "basis": basis,
                "sizing_mode": sizing_mode,
                "equity_basis_cap_jpy": group["equity_basis_cap_jpy"].dropna().iloc[0] if group["equity_basis_cap_jpy"].notna().any() else None,
                "date_from": args.date_from,
                "date_to": args.date_to,
                "initial_capital_jpy": float(args.initial_capital_jpy),
                "final_equity_jpy": final_equity,
                "total_return_pct": final_equity / float(args.initial_capital_jpy) - 1.0,
                "cagr": cagr(initial_capital_jpy=float(args.initial_capital_jpy), final_equity_jpy=final_equity, start=date_from, end=date_to),
                "max_dd_pct": max_drawdown_pct(group.sort_values("timestamp")["equity_jpy"]),
            }
        )
    summary = pd.DataFrame(summary_rows)
    if not summary.empty:
        for sizing_mode in summary["sizing_mode"].dropna().unique():
            mask = summary["sizing_mode"].eq(sizing_mode)
            subset = summary.loc[mask]
            if set(subset["basis"]) >= {"deferred_withdrawal", "immediate_withdrawal"}:
                deferred = float(subset.loc[subset["basis"] == "deferred_withdrawal", "final_equity_jpy"].iloc[0])
                immediate = float(subset.loc[subset["basis"] == "immediate_withdrawal", "final_equity_jpy"].iloc[0])
                summary.loc[mask, "final_equity_deferred_jpy"] = deferred
                summary.loc[mask, "final_equity_immediate_jpy"] = immediate
                summary.loc[mask, "deferred_reinvestment_benefit_jpy"] = deferred - immediate
                summary.loc[mask, "deferred_reinvestment_benefit_pct"] = deferred / immediate - 1.0 if immediate != 0 else pd.NA

    write_csv(summary, out_dir / "summary.csv")
    write_csv(yearly, out_dir / "yearly_allocation.csv")
    write_csv(cashflows, out_dir / "cashflow_events.csv")
    write_csv(equity_curve, out_dir / "equity_curve.csv")
    write_csv(level_history, out_dir / "setting_level_history.csv")
    write_csv(trade_ledger, out_dir / "trade_ledger.csv")
    write_csv(input_summary, out_dir / "input_summary.csv")
    write_json(vars(args), out_dir / "params.json")
    write_json(
        {
            "experiment_code": "E013",
            "generated_at": datetime.now().isoformat(),
            "git_commit": git_commit(),
            "runtime_config_dir": args.runtime_config_dir,
            "qualify_out_dir": args.qualify_out_dir,
            "input_setting_files": [setting.source_file for setting in settings],
        },
        out_dir / "metadata.json",
    )
    return {
        "summary": summary,
        "yearly_allocation": yearly,
        "cashflow_events": cashflows,
        "equity_curve": equity_curve,
        "setting_level_history": level_history,
    }


def main() -> None:
    args = parse_args()
    result = run(args)
    print(f"[WRITE] {args.out_dir}")
    print(result["summary"].to_string(index=False))


if __name__ == "__main__":
    main()
