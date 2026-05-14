from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from portfolio.common.conflict import simulate_conflict_100pct
from portfolio.common.capital import max_drawdown_pct
from portfolio.common.initial_levels import add_initial_level_args, apply_initial_levels
from portfolio.common.inputs import load_settings
from portfolio.common.ledger import build_trade_ledger
from portfolio.common.reporting import concat_frames, ensure_out_dir, git_commit, write_csv, write_json
from portfolio.common.risk import max_drawdown_jpy_from_equity, trade_risk_metrics
from portfolio.common.unit_level import level_pivot, simulate_level_basis


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run portfolio E012 unit level simulation.")
    parser.add_argument("--runtime-config-dir", default="runtime/config")
    parser.add_argument("--qualify-out-dir", default="qualify/out")
    parser.add_argument("--out-dir", default="portfolio/out/E012/latest")
    parser.add_argument("--date-from", default="2019-01-01")
    parser.add_argument("--date-to", default="2025-12-31")
    parser.add_argument("--initial-capital-jpy", type=float, required=True)
    parser.add_argument("--include-disabled", action="store_true")
    add_initial_level_args(parser)
    parser.add_argument("--basis", choices=["realized_after_conflict", "theoretical_without_conflict", "both"], default="both")
    return parser.parse_args()


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

    basis_frames: list[pd.DataFrame] = []
    monthly_frames: list[pd.DataFrame] = []
    level_frames: list[pd.DataFrame] = []
    bases = ["realized_after_conflict", "theoretical_without_conflict"] if args.basis == "both" else [args.basis]
    sizing_runs = [
        ("unlimited", None),
        ("equity_basis_cap_100m_jpy", 100_000_000.0),
    ]
    conflict_ledger = pd.DataFrame()
    if "realized_after_conflict" in bases:
        simulated, _, _ = simulate_conflict_100pct(ledger, initial_capital_jpy=float(args.initial_capital_jpy))
        conflict_ledger = simulated.loc[simulated["executed"]].copy() if not simulated.empty else simulated
    for basis in bases:
        source = conflict_ledger if basis == "realized_after_conflict" else ledger
        for sizing_mode, equity_basis_cap_jpy in sizing_runs:
            trade_df, monthly_df, level_df = simulate_level_basis(
                source,
                settings=settings_df,
                initial_capital_jpy=float(args.initial_capital_jpy),
                basis=basis,
                sizing_mode=sizing_mode,
                equity_basis_cap_jpy=equity_basis_cap_jpy,
                date_from=date_from,
                date_to=date_to,
            )
            basis_frames.append(trade_df)
            monthly_frames.append(monthly_df)
            level_frames.append(level_df)

    trade_ledger = concat_frames(basis_frames)
    monthly = concat_frames(monthly_frames)
    level_history = concat_frames(level_frames)
    pivot = level_pivot(level_history)
    setting_rows = []
    if not trade_ledger.empty:
        final_levels = (
            level_history.sort_values("decision_month")
            .groupby(["basis", "sizing_mode", "setting_id"], dropna=False)["next_level"]
            .last()
            .to_dict()
            if not level_history.empty
            else {}
        )
        for keys, group in trade_ledger.groupby(["basis", "sizing_mode", "setting_id"], dropna=False):
            basis, sizing_mode, setting_id = keys
            risk_group = trade_risk_metrics(group["pnl_jpy"])
            setting_rows.append(
                {
                    "basis": basis,
                    "sizing_mode": sizing_mode,
                    "setting_id": setting_id,
                    "pnl_jpy_sum": float(pd.to_numeric(group["pnl_jpy"], errors="coerce").sum()),
                    "final_level": final_levels.get((basis, sizing_mode, setting_id)),
                    **risk_group,
                }
            )
    setting_summary = pd.DataFrame(setting_rows)

    summary_rows = []
    if not trade_ledger.empty:
        for (basis, sizing_mode), group in trade_ledger.groupby(["basis", "sizing_mode"], dropna=False):
            curve = group.sort_values("exit_ts")["equity_jpy"]
            risk_group = trade_risk_metrics(group["pnl_jpy"])
            monthly_group = monthly.loc[(monthly["basis"] == basis) & (monthly["sizing_mode"] == sizing_mode)] if not monthly.empty else pd.DataFrame()
            monthly_setting = (
                monthly_group.groupby("decision_month", dropna=False)["cum_jpy_month"].sum()
                if not monthly_group.empty
                else pd.Series(dtype=float)
            )
            final_equity = float(pd.to_numeric(curve, errors="coerce").iloc[-1])
            summary_rows.append(
                {
                    "basis": basis,
                    "sizing_mode": sizing_mode,
                    "trade_count": int(len(group)),
                    "pnl_jpy_sum": float(pd.to_numeric(group["pnl_jpy"], errors="coerce").sum()),
                    "final_equity_jpy": final_equity,
                    "initial_capital_jpy": float(args.initial_capital_jpy),
                    "date_from": args.date_from,
                    "date_to": args.date_to,
                    "total_return_pct": final_equity / float(args.initial_capital_jpy) - 1.0,
                    "max_dd_pct": max_drawdown_pct(curve),
                    "max_dd_jpy": max_drawdown_jpy_from_equity(curve),
                    "worst_month_pnl_jpy": float(monthly_setting.min()) if not monthly_setting.empty else 0.0,
                    "best_month_pnl_jpy": float(monthly_setting.max()) if not monthly_setting.empty else 0.0,
                    **risk_group,
                }
            )
    summary = pd.DataFrame(summary_rows)

    write_csv(summary, out_dir / "summary.csv")
    write_csv(setting_summary, out_dir / "setting_summary.csv")
    write_csv(monthly, out_dir / "setting_monthly_pnl.csv")
    write_csv(level_history, out_dir / "setting_level_history.csv")
    write_csv(pivot, out_dir / "setting_level_pivot.csv")
    write_csv(trade_ledger, out_dir / "trade_ledger.csv")
    write_csv(input_summary, out_dir / "input_summary.csv")
    # E012 trade-level equity is already in trade_ledger; keep a slim curve too.
    equity_curve = (
        trade_ledger[["basis", "sizing_mode", "equity_basis_cap_jpy", "exit_ts", "setting_id", "equity_jpy", "pnl_jpy"]].rename(
            columns={"exit_ts": "timestamp"}
        )
        if not trade_ledger.empty
        else pd.DataFrame()
    )
    write_csv(equity_curve, out_dir / "equity_curve.csv")
    write_json(vars(args), out_dir / "params.json")
    write_json(
        {
            "experiment_code": "E012",
            "generated_at": datetime.now().isoformat(),
            "git_commit": git_commit(),
            "runtime_config_dir": args.runtime_config_dir,
            "qualify_out_dir": args.qualify_out_dir,
            "input_setting_files": [setting.source_file for setting in settings],
        },
        out_dir / "metadata.json",
    )
    return {"summary": summary, "setting_level_history": level_history, "trade_ledger": trade_ledger}


def main() -> None:
    args = parse_args()
    result = run(args)
    print(f"[WRITE] {args.out_dir}")
    print(result["summary"].to_string(index=False))


if __name__ == "__main__":
    main()
