from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from portfolio.common.capital import compute_units, cagr, max_drawdown_pct, pnl_jpy
from portfolio.common.conflict import conflict_blocker_summary, simulate_conflict_100pct
from portfolio.common.inputs import load_settings
from portfolio.common.ledger import build_trade_ledger
from portfolio.common.reporting import concat_frames, ensure_out_dir, git_commit, write_csv, write_json
from portfolio.common.risk import max_drawdown_jpy_from_equity, trade_risk_metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run portfolio E011 conflict simulation.")
    parser.add_argument("--runtime-config-dir", default="runtime/config")
    parser.add_argument("--qualify-out-dir", default="qualify/out")
    parser.add_argument("--out-dir", default="portfolio/out/E011/latest")
    parser.add_argument("--date-from", default="2019-01-01")
    parser.add_argument("--date-to", default="2025-12-31")
    parser.add_argument("--initial-capital-jpy", type=float, required=True)
    parser.add_argument("--include-disabled", action="store_true")
    return parser.parse_args()


def run(args: argparse.Namespace) -> dict[str, pd.DataFrame]:
    out_dir = ensure_out_dir(args.out_dir)
    date_from = pd.to_datetime(args.date_from).date()
    date_to = pd.to_datetime(args.date_to).date()
    settings = load_settings(args.runtime_config_dir, include_disabled=args.include_disabled)
    ledger, input_summary = build_trade_ledger(
        settings,
        qualify_out_dir=args.qualify_out_dir,
        date_from=date_from,
        date_to=date_to,
    )
    missing_margin = ledger["margin_ratio_target"].isna() if not ledger.empty else pd.Series(dtype=bool)
    if not ledger.empty and bool(missing_margin.any()):
        ledger = ledger.loc[~missing_margin].copy()

    runs = [
        ("unlimited", None),
        ("equity_basis_cap_100m_jpy", 100_000_000.0),
    ]
    simulated_frames: list[pd.DataFrame] = []
    conflict_frames: list[pd.DataFrame] = []
    equity_frames: list[pd.DataFrame] = []
    summary_rows: list[dict[str, object]] = []
    setting_frames: list[pd.DataFrame] = []
    start_ts = pd.to_datetime(args.date_from)
    end_ts = pd.to_datetime(args.date_to)

    for basis, equity_basis_cap_jpy in runs:
        simulated, conflict_events, equity_curve = simulate_conflict_100pct(
            ledger,
            initial_capital_jpy=float(args.initial_capital_jpy),
            equity_basis_cap_jpy=equity_basis_cap_jpy,
            basis=basis,
        )
        if not conflict_events.empty:
            conflict_events["basis"] = basis
        simulated_frames.append(simulated)
        conflict_frames.append(conflict_events)
        equity_frames.append(equity_curve)
        executed = simulated.loc[simulated["executed"]] if not simulated.empty else pd.DataFrame()
        blocked = simulated.loc[simulated["blocked"]] if not simulated.empty else pd.DataFrame()
        fixed_initial_units = []
        fixed_initial_pnl = []
        for _, trade in simulated.iterrows():
            units = compute_units(
                equity_jpy=min(float(args.initial_capital_jpy), float(equity_basis_cap_jpy))
                if equity_basis_cap_jpy is not None
                else float(args.initial_capital_jpy),
                entry_price=float(trade["entry_price"]),
                margin_ratio_target=float(trade["margin_ratio_target"]),
                size_scale_pct=100.0,
            )
            fixed_initial_units.append(units)
            fixed_initial_pnl.append(pnl_jpy(units=units, pnl_pips=float(trade["pnl_pips"])))
        simulated["fixed_initial_units"] = fixed_initial_units
        simulated["fixed_initial_pnl_jpy"] = fixed_initial_pnl
        executed = simulated.loc[simulated["executed"]]
        blocked = simulated.loc[simulated["blocked"]]
        simulated_frames[-1] = simulated
        theoretical_pnl = float(pd.to_numeric(simulated.get("pnl_jpy", pd.Series(dtype=float)), errors="coerce").sum())
        executed_pnl = float(pd.to_numeric(executed.get("pnl_jpy", pd.Series(dtype=float)), errors="coerce").sum())
        blocked_pnl = float(pd.to_numeric(blocked.get("pnl_jpy", pd.Series(dtype=float)), errors="coerce").sum())
        fixed_initial_theoretical_pnl = float(pd.to_numeric(simulated.get("fixed_initial_pnl_jpy", pd.Series(dtype=float)), errors="coerce").sum())
        fixed_initial_executed_pnl = float(pd.to_numeric(executed.get("fixed_initial_pnl_jpy", pd.Series(dtype=float)), errors="coerce").sum())
        fixed_initial_blocked_pnl = float(pd.to_numeric(blocked.get("fixed_initial_pnl_jpy", pd.Series(dtype=float)), errors="coerce").sum())
        final_equity = float(equity_curve["equity_jpy"].iloc[-1]) if not equity_curve.empty else float(args.initial_capital_jpy)
        risk = trade_risk_metrics(executed.get("pnl_jpy", pd.Series(dtype=float)))
        summary_rows.append(
            {
                "basis": basis,
                "date_from": args.date_from,
                "date_to": args.date_to,
                "initial_capital_jpy": float(args.initial_capital_jpy),
                "equity_basis_cap_jpy": equity_basis_cap_jpy,
                "final_equity_jpy": final_equity,
                "total_return_pct": final_equity / float(args.initial_capital_jpy) - 1.0,
                "cagr": cagr(initial_capital_jpy=float(args.initial_capital_jpy), final_equity_jpy=final_equity, start=start_ts, end=end_ts),
                "max_dd_pct": max_drawdown_pct(equity_curve["equity_jpy"]) if not equity_curve.empty else 0.0,
                "max_dd_jpy": max_drawdown_jpy_from_equity(equity_curve["equity_jpy"]) if not equity_curve.empty else 0.0,
                "peak_equity_jpy": float(pd.to_numeric(equity_curve["equity_jpy"], errors="coerce").max()) if not equity_curve.empty else float(args.initial_capital_jpy),
                "min_equity_jpy": float(pd.to_numeric(equity_curve["equity_jpy"], errors="coerce").min()) if not equity_curve.empty else float(args.initial_capital_jpy),
                "trade_count_theoretical": int(len(simulated)),
                "trade_count_executed": int(len(executed)),
                "trade_count_blocked": int(len(blocked)),
                "win_rate": risk["win_rate"],
                "profit_factor": risk["profit_factor"],
                "avg_pnl_jpy": risk["avg_pnl_jpy"],
                "median_pnl_jpy": risk["median_pnl_jpy"],
                "best_trade_pnl_jpy": risk["best_trade_pnl_jpy"],
                "worst_trade_pnl_jpy": risk["worst_trade_pnl_jpy"],
                "max_consecutive_losses": risk["max_consecutive_losses"],
                "trade_pnl_max_dd_jpy": risk["trade_pnl_max_dd_jpy"],
                "theoretical_pnl_jpy": theoretical_pnl,
                "executed_pnl_jpy": executed_pnl,
                "blocked_pnl_jpy": blocked_pnl,
                "conflict_drag_jpy": theoretical_pnl - executed_pnl,
                "fixed_initial_final_equity_jpy": float(args.initial_capital_jpy) + fixed_initial_executed_pnl,
                "fixed_initial_theoretical_pnl_jpy": fixed_initial_theoretical_pnl,
                "fixed_initial_executed_pnl_jpy": fixed_initial_executed_pnl,
                "fixed_initial_blocked_pnl_jpy": fixed_initial_blocked_pnl,
                "fixed_initial_conflict_drag_jpy": fixed_initial_theoretical_pnl - fixed_initial_executed_pnl,
            }
        )
        if not simulated.empty:
            setting_rows = []
            for (group_basis, setting_id), group in simulated.groupby(["basis", "setting_id"], dropna=False):
                executed_group = group.loc[group["executed"]].copy()
                risk_group = trade_risk_metrics(executed_group.get("pnl_jpy", pd.Series(dtype=float)))
                setting_rows.append(
                    {
                        "basis": group_basis,
                        "setting_id": setting_id,
                        "trade_count": int(len(group)),
                        "executed_count": int(group["executed"].sum()),
                        "blocked_count": int(group["blocked"].sum()),
                        "executed_pnl_jpy_sum": float(pd.to_numeric(executed_group.get("pnl_jpy", pd.Series(dtype=float)), errors="coerce").sum()),
                        "blocked_pnl_jpy_sum": float(pd.to_numeric(group.loc[group["blocked"], "pnl_jpy"], errors="coerce").sum()),
                        **risk_group,
                    }
                )
            setting_summary_basis = pd.DataFrame(setting_rows)
            setting_frames.append(setting_summary_basis)

    simulated_all = concat_frames(simulated_frames)
    conflict_events = concat_frames(conflict_frames)
    equity_curve = concat_frames(equity_frames)
    blocker_summary = (
        concat_frames(
            [
                conflict_blocker_summary(events).assign(basis=basis)
                for basis, events in zip([item[0] for item in runs], conflict_frames)
                if not events.empty
            ]
        )
        if conflict_frames
        else pd.DataFrame()
    )
    summary = pd.DataFrame(summary_rows)
    setting_summary = concat_frames(setting_frames)

    write_csv(summary, out_dir / "summary.csv")
    write_csv(setting_summary, out_dir / "setting_summary.csv")
    write_csv(conflict_events, out_dir / "conflict_events.csv")
    write_csv(blocker_summary, out_dir / "conflict_blocker_summary.csv")
    write_csv(equity_curve, out_dir / "equity_curve.csv")
    write_csv(simulated_all, out_dir / "trade_ledger.csv")
    write_csv(input_summary, out_dir / "input_summary.csv")
    write_json(vars(args), out_dir / "params.json")
    write_json(
        {
            "experiment_code": "E011",
            "generated_at": datetime.now().isoformat(),
            "git_commit": git_commit(),
            "runtime_config_dir": args.runtime_config_dir,
            "qualify_out_dir": args.qualify_out_dir,
            "input_setting_files": [setting.source_file for setting in settings],
            "input_trade_files": sorted(simulated_all["trade_source_file"].dropna().unique().tolist()) if not simulated_all.empty else [],
        },
        out_dir / "metadata.json",
    )
    return {
        "summary": summary,
        "setting_summary": setting_summary,
        "conflict_events": conflict_events,
        "equity_curve": equity_curve,
        "trade_ledger": simulated_all,
    }


def main() -> None:
    args = parse_args()
    result = run(args)
    print(f"[WRITE] {args.out_dir}")
    print(result["summary"].to_string(index=False))


if __name__ == "__main__":
    main()
