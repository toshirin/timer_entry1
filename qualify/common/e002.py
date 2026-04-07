from __future__ import annotations

from dataclasses import asdict
import math
from pathlib import Path

import pandas as pd

from timer_entry.backtest_1m import run_backtest_1m
from timer_entry.minute_data import load_trading_days

from .e001 import _eligible_days_by_segment, _eligible_feature_rows, _filter_days
from .io import ensure_run_layout, write_json
from .params import E002Params
from .reporting import (
    DEFAULT_IN_YEARS,
    DEFAULT_OUT_YEARS,
    build_e002_summary,
    build_sanity_summary,
    build_split_summary,
    build_year_summary,
)


def _comparison_trade_frame(
    *,
    comparison_label: str,
    filter_label: str,
    tp_pips: float,
    sl_pips: float,
    result: object,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for trade in result.trades:  # type: ignore[attr-defined]
        row = trade.to_dict()
        row["comparison_label"] = comparison_label
        row["filter_label"] = filter_label
        row["tp_pips"] = float(tp_pips)
        row["sl_pips"] = float(sl_pips)
        row["year"] = int(str(trade.date_local)[:4])
        rows.append(row)
    return pd.DataFrame(rows)


def _comparison_summary_row(
    *,
    comparison_label: str,
    filter_label: str,
    tp_pips: float,
    sl_pips: float,
    input_pass_stability_gate: bool,
    result: object,
) -> dict[str, object]:
    trades = pd.DataFrame([trade.to_dict() for trade in result.trades])  # type: ignore[attr-defined]
    if trades.empty:
        in_gross_pips = 0.0
        out_gross_pips = 0.0
        total_gross_pips = 0.0
        top1_share_of_total = math.nan
        ex_top10_gross_pips = 0.0
    else:
        trades["year"] = trades["date_local"].astype(str).str[:4].astype(int)
        pnl = pd.to_numeric(trades["pnl_pips"], errors="coerce")
        total_gross_pips = float(pnl.sum())
        in_gross_pips = float(trades.loc[trades["year"].isin(DEFAULT_IN_YEARS), "pnl_pips"].sum())
        out_gross_pips = float(trades.loc[trades["year"].isin(DEFAULT_OUT_YEARS), "pnl_pips"].sum())
        top1 = float(pnl.max()) if not pnl.empty else math.nan
        top10 = float(pnl.sort_values(ascending=False).head(10).sum()) if not pnl.empty else 0.0
        top1_share_of_total = float(top1 / total_gross_pips) if total_gross_pips != 0.0 else math.nan
        ex_top10_gross_pips = float(total_gross_pips - top10)

    summary = result.summary.to_dict()  # type: ignore[attr-defined]
    summary.update(
        {
            "comparison_label": comparison_label,
            "filter_label": filter_label,
            "tp_pips": float(tp_pips),
            "sl_pips": float(sl_pips),
            "input_pass_stability_gate": input_pass_stability_gate,
            "in_gross_pips": round(in_gross_pips, 6),
            "out_gross_pips": round(out_gross_pips, 6),
            "top1_share_of_total": top1_share_of_total,
            "ex_top10_gross_pips": round(ex_top10_gross_pips, 6),
        }
    )
    return summary


def run_e002(
    *,
    params: E002Params,
    dataset_dir: str | Path,
    out_dir: str | Path,
    years: list[int],
    allow_gate_fail: bool = False,
) -> dict[str, pd.DataFrame]:
    if not params.pass_stability_gate and not allow_gate_fail:
        raise ValueError("pass_stability_gate is False; rerun with explicit override if this is intentional")

    paths = ensure_run_layout(out_dir)
    days, load_summary = load_trading_days(years, dataset_dir=dataset_dir, session_tz=params.market_tz)  # type: ignore[arg-type]
    filtered_days = _filter_days(days, date_from=params.date_from, date_to=params.date_to)
    feature_rows = _eligible_feature_rows(filtered_days, params)  # type: ignore[arg-type]
    eligible_days_by_segment = _eligible_days_by_segment(feature_rows)

    all_trade_frames: list[pd.DataFrame] = []
    summary_rows: list[dict[str, object]] = []
    sanity_rows: list[dict[str, object]] = []
    filter_label = ",".join(params.baseline.filter_labels)

    for sl_pips in params.sl_values:
        for tp_pips in params.tp_values:
            comparison_label = params.comparison_label(tp_pips=tp_pips, sl_pips=sl_pips)
            setting = params.to_strategy_setting(tp_pips=tp_pips, sl_pips=sl_pips)
            result = run_backtest_1m(
                filtered_days,
                setting,
                time_jst_fallback_count=load_summary.time_jst_fallback_count,
                duplicate_clock_removed_count=load_summary.duplicate_clock_removed_count,
            )
            all_trade_frames.append(
                _comparison_trade_frame(
                    comparison_label=comparison_label,
                    filter_label=filter_label,
                    tp_pips=tp_pips,
                    sl_pips=sl_pips,
                    result=result,
                )
            )
            summary_rows.append(
                _comparison_summary_row(
                    comparison_label=comparison_label,
                    filter_label=filter_label,
                    tp_pips=tp_pips,
                    sl_pips=sl_pips,
                    input_pass_stability_gate=params.pass_stability_gate,
                    result=result,
                )
            )
            sanity_row = result.sanity.to_dict()
            sanity_row["comparison_label"] = comparison_label
            sanity_row["filter_label"] = filter_label
            sanity_row["tp_pips"] = float(tp_pips)
            sanity_row["sl_pips"] = float(sl_pips)
            sanity_rows.append(sanity_row)

    trades_df = pd.concat(all_trade_frames, ignore_index=True) if all_trade_frames else pd.DataFrame()
    summary_df = build_e002_summary(summary_rows)
    split_df = build_split_summary(trades_df, eligible_days_by_segment=eligible_days_by_segment)
    year_df = build_year_summary(trades_df)
    sanity_df = build_sanity_summary(sanity_rows)

    metadata = {
        "experiment_code": params.experiment_code,
        "variant_code": params.variant_code,
        "slot_id": params.slot_id,
        "side": params.side,
        "baseline_filter_labels": list(params.baseline.filter_labels),
        "tp_values": list(params.tp_values),
        "sl_values": list(params.sl_values),
        "pass_stability_gate": params.pass_stability_gate,
        "allow_gate_fail": allow_gate_fail,
        "dataset_dir": str(dataset_dir),
        "years": years,
        "date_from": params.date_from,
        "date_to": params.date_to,
        "eligible_days_by_segment": eligible_days_by_segment,
        "load_summary": asdict(load_summary),
        "notes": params.notes,
    }

    write_json(paths["metadata_json"], metadata)
    write_json(paths["params_json"], params.to_dict())
    summary_df.to_csv(paths["summary_csv"], index=False)
    split_df.to_csv(paths["split_summary_csv"], index=False)
    year_df.to_csv(paths["year_summary_csv"], index=False)
    trades_df.to_csv(paths["trades_csv"], index=False)
    sanity_df.to_csv(paths["sanity_csv"], index=False)

    return {
        "summary_df": summary_df,
        "split_df": split_df,
        "year_df": year_df,
        "trades_df": trades_df,
        "sanity_df": sanity_df,
    }
