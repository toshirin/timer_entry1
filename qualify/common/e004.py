from __future__ import annotations

from dataclasses import asdict
import math
from pathlib import Path

import pandas as pd

from timer_entry.backtest_1m import BacktestRunResult
from timer_entry.minute_data import load_trading_days

from .e001 import _eligible_days_by_segment, _eligible_feature_rows, _filter_days
from .io import ensure_run_layout, write_json
from .params import E004Params
from .reporting import (
    DEFAULT_IN_YEARS,
    DEFAULT_OUT_YEARS,
    build_e004_summary,
    build_sanity_summary,
    build_split_summary,
    build_year_summary,
)
from .tick_replay import generate_e004_signal_days, run_tick_replay_batch


def _minute_trade_frame(
    *,
    comparison_label: str,
    filter_label: str,
    minute_result: BacktestRunResult,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for trade in minute_result.trades:
        row = trade.to_dict()
        row["comparison_label"] = comparison_label
        row["filter_label"] = filter_label
        row["year"] = int(str(trade.date_local)[:4])
        rows.append(row)
    return pd.DataFrame(rows)


def _build_trade_comparison(*, signals_df: pd.DataFrame, tick_df: pd.DataFrame) -> pd.DataFrame:
    if signals_df.empty:
        return pd.DataFrame()
    if tick_df.empty:
        tick_df = pd.DataFrame(
            columns=[
                "trade_id",
                "date_local",
                "year",
                "comparison_label",
                "side",
                "market_tz",
                "filter_label",
                "tp_pips",
                "sl_pips",
                "entry_time",
                "entry_price",
                "exit_time",
                "exit_price",
                "exit_reason",
                "pnl_pips",
            ]
        )

    merged = signals_df.merge(
        tick_df,
        on=["trade_id", "date_local", "year", "comparison_label", "side", "market_tz", "filter_label", "tp_pips", "sl_pips"],
        how="left",
        suffixes=("_minute", ""),
    )
    merged["minute_entry_delta_pips"] = (
        pd.to_numeric(merged["entry_price"], errors="coerce") - pd.to_numeric(merged["minute_entry_price"], errors="coerce")
    ) / 0.01
    merged["minute_exit_delta_pips"] = (
        pd.to_numeric(merged["exit_price"], errors="coerce") - pd.to_numeric(merged["minute_exit_price"], errors="coerce")
    ) / 0.01
    merged["minute_pnl_delta_pips"] = pd.to_numeric(merged["pnl_pips"], errors="coerce") - pd.to_numeric(
        merged["minute_pnl_pips"], errors="coerce"
    )
    return merged


def _merge_segment_summary(
    *,
    tick_df: pd.DataFrame,
    minute_df: pd.DataFrame,
    eligible_days_by_segment: dict[str, int],
) -> pd.DataFrame:
    tick_split = build_split_summary(tick_df, eligible_days_by_segment=eligible_days_by_segment)
    minute_split = build_split_summary(minute_df, eligible_days_by_segment=eligible_days_by_segment).rename(
        columns={
            "trade_count": "minute_trade_count",
            "gross_pips": "minute_gross_pips",
            "mean_pips": "minute_mean_pips",
            "win_rate": "minute_win_rate",
            "profit_factor": "minute_profit_factor",
            "max_dd_pips": "minute_max_dd_pips",
        }
    )
    merged = tick_split.merge(minute_split, on=["comparison_label", "segment", "eligible_day_count"], how="outer")
    if merged.empty:
        return merged
    merged["delta_gross_pips"] = pd.to_numeric(merged["gross_pips"], errors="coerce") - pd.to_numeric(
        merged["minute_gross_pips"], errors="coerce"
    )
    return merged


def _merge_year_summary(*, tick_df: pd.DataFrame, minute_df: pd.DataFrame) -> pd.DataFrame:
    tick_year = build_year_summary(tick_df)
    minute_year = build_year_summary(minute_df).rename(
        columns={
            "trade_count": "minute_trade_count",
            "gross_pips": "minute_gross_pips",
            "mean_pips": "minute_mean_pips",
            "median_pips": "minute_median_pips",
            "std_pips": "minute_std_pips",
            "win_rate": "minute_win_rate",
            "profit_factor": "minute_profit_factor",
            "max_dd_pips": "minute_max_dd_pips",
        }
    )
    merged = tick_year.merge(minute_year, on=["comparison_label", "year"], how="outer")
    if merged.empty:
        return merged
    merged["delta_gross_pips"] = pd.to_numeric(merged["gross_pips"], errors="coerce") - pd.to_numeric(
        merged["minute_gross_pips"], errors="coerce"
    )
    return merged


def _safe_gross_by_years(df: pd.DataFrame, years: tuple[int, ...]) -> float:
    if df.empty:
        return 0.0
    return float(df.loc[df["year"].isin(years), "pnl_pips"].sum())


def _aggregate_tick_sanity(
    *,
    comparison_label: str,
    params: E004Params,
    tick_rows: pd.DataFrame,
    minute_sanity: object,
    load_summary: object,
) -> pd.DataFrame:
    filter_label = ",".join(params.baseline.filter_labels)
    if tick_rows.empty:
        valid = pd.DataFrame(
            [
                {
                    "entry_equals_exit_all_flag": False,
                    "entry_equals_exit_sl_flag": False,
                    "tp_sl_same_tick_flag": False,
                    "forced_exit_missing_flag": False,
                    "tick_not_found_flag": False,
                    "entry_after_forced_exit_flag": False,
                }
            ]
        )
        forced_exit_count = 0
    else:
        valid = tick_rows.fillna(False)
        forced_exit_count = int((tick_rows["exit_reason"] == "forced_exit").sum())
    row = minute_sanity.to_dict()  # type: ignore[attr-defined]
    row.update(
        {
            "comparison_label": comparison_label,
            "filter_label": filter_label,
            "tp_pips": float(params.baseline.tp_pips),
            "sl_pips": float(params.baseline.sl_pips),
            "forced_exit_clock_local": params.baseline.forced_exit_clock_local,
            "slippage_mode": params.slippage_mode,
            "fixed_slippage_pips": float(params.fixed_slippage_pips),
            "entry_delay_seconds": int(params.entry_delay_seconds),
            "entry_equals_exit_count": int(valid["entry_equals_exit_all_flag"].sum()),
            "entry_equals_exit_sl_count": int(valid["entry_equals_exit_sl_flag"].sum()),
            "same_bar_conflict_count": int(valid["tp_sl_same_tick_flag"].sum()),
            "same_bar_unresolved_count": int(valid["tp_sl_same_tick_flag"].sum()),
            "forced_exit_count": forced_exit_count,
            "forced_exit_missing_count": int(valid["forced_exit_missing_flag"].sum()),
            "feature_skip_count": 0,
            "time_jst_fallback_count": load_summary.time_jst_fallback_count,  # type: ignore[attr-defined]
            "duplicate_clock_removed_count": load_summary.duplicate_clock_removed_count,  # type: ignore[attr-defined]
            "notes": (
                f"tick_not_found_count={int(valid['tick_not_found_flag'].sum())}, "
                f"entry_after_forced_exit_count={int(valid['entry_after_forced_exit_flag'].sum())}"
            ),
        }
    )
    return build_sanity_summary([row])


def _summary_row(
    *,
    comparison_label: str,
    params: E004Params,
    eligible_days_by_segment: dict[str, int],
    signals_df: pd.DataFrame,
    tick_trade_df: pd.DataFrame,
    minute_trade_df: pd.DataFrame,
    tick_rows: pd.DataFrame,
) -> dict[str, object]:
    def _profit_factor(values: pd.Series) -> float:
        gains = float(values[values > 0.0].sum())
        losses = float(-values[values < 0.0].sum())
        if losses == 0.0:
            return math.inf if gains > 0.0 else math.nan
        return gains / losses

    def _max_dd(values: pd.Series) -> float:
        if values.empty:
            return math.nan
        equity = values.cumsum()
        dd = equity - equity.cummax()
        return float(dd.min())

    def _annualized(trades: pd.DataFrame) -> float:
        if trades.empty:
            return math.nan
        year_count = len(sorted(set(trades["year"].astype(int))))
        gross = float(trades["pnl_pips"].sum())
        return gross / year_count if year_count > 0 else math.nan

    tick_pnl = pd.to_numeric(tick_trade_df["pnl_pips"], errors="coerce") if not tick_trade_df.empty else pd.Series(dtype=float)
    minute_pnl = (
        pd.to_numeric(minute_trade_df["pnl_pips"], errors="coerce") if not minute_trade_df.empty else pd.Series(dtype=float)
    )
    tick_gross = float(tick_pnl.sum()) if not tick_pnl.empty else 0.0
    minute_gross = float(minute_pnl.sum()) if not minute_pnl.empty else 0.0
    tick_in = _safe_gross_by_years(tick_trade_df, DEFAULT_IN_YEARS)
    tick_out = _safe_gross_by_years(tick_trade_df, DEFAULT_OUT_YEARS)
    minute_in = _safe_gross_by_years(minute_trade_df, DEFAULT_IN_YEARS)
    minute_out = _safe_gross_by_years(minute_trade_df, DEFAULT_OUT_YEARS)

    pass_stability_gate = bool(tick_in > 0.0 and tick_out > 0.0)
    return {
        "comparison_label": comparison_label,
        "filter_label": ",".join(params.baseline.filter_labels),
        "tp_pips": float(params.baseline.tp_pips),
        "sl_pips": float(params.baseline.sl_pips),
        "forced_exit_clock_local": params.baseline.forced_exit_clock_local,
        "slippage_mode": params.slippage_mode,
        "fixed_slippage_pips": float(params.fixed_slippage_pips),
        "entry_delay_seconds": int(params.entry_delay_seconds),
        "input_pass_stability_gate": params.pass_stability_gate,
        "eligible_day_count": int(eligible_days_by_segment["full"]),
        "signal_day_count": int(len(signals_df)),
        "trade_count": int(len(tick_trade_df)),
        "minute_trade_count": int(len(minute_trade_df)),
        "gross_pips": tick_gross,
        "minute_gross_pips": minute_gross,
        "delta_gross_pips": tick_gross - minute_gross,
        "in_gross_pips": tick_in,
        "out_gross_pips": tick_out,
        "minute_in_gross_pips": minute_in,
        "minute_out_gross_pips": minute_out,
        "win_rate": float((tick_pnl > 0.0).mean()) if not tick_pnl.empty else math.nan,
        "minute_win_rate": float((minute_pnl > 0.0).mean()) if not minute_pnl.empty else math.nan,
        "profit_factor": float(_profit_factor(tick_pnl)),
        "minute_profit_factor": float(_profit_factor(minute_pnl)),
        "max_dd_pips": float(_max_dd(tick_pnl)),
        "minute_max_dd_pips": float(_max_dd(minute_pnl)),
        "annualized_pips": float(_annualized(tick_trade_df)),
        "minute_annualized_pips": float(_annualized(minute_trade_df)),
        "pass_stability_gate": pass_stability_gate,
        "tick_not_found_count": int(tick_rows["tick_not_found_flag"].fillna(False).sum()) if not tick_rows.empty else 0,
        "forced_exit_missing_count": int(tick_rows["forced_exit_missing_flag"].fillna(False).sum()) if not tick_rows.empty else 0,
        "entry_after_forced_exit_count": int(tick_rows["entry_after_forced_exit_flag"].fillna(False).sum())
        if not tick_rows.empty
        else 0,
    }


def run_e004(
    *,
    params: E004Params,
    dataset_dir: str | Path,
    ticks_dir: str | Path,
    out_dir: str | Path,
    years: list[int],
    jobs: int = 1,
    allow_gate_fail: bool = False,
) -> dict[str, pd.DataFrame]:
    if not params.pass_stability_gate and not allow_gate_fail:
        raise ValueError("pass_stability_gate is False; rerun with explicit override if this is intentional")

    paths = ensure_run_layout(out_dir)
    days, load_summary = load_trading_days(years, dataset_dir=dataset_dir, session_tz=params.market_tz)  # type: ignore[arg-type]
    filtered_days = _filter_days(days, date_from=params.date_from, date_to=params.date_to)
    feature_rows = _eligible_feature_rows(filtered_days, params)  # type: ignore[arg-type]
    eligible_days_by_segment = _eligible_days_by_segment(feature_rows)

    signals, minute_result = generate_e004_signal_days(filtered_days, params=params, load_summary=load_summary)
    comparison_label = params.comparison_label()
    filter_label = ",".join(params.baseline.filter_labels)

    signals_df = pd.DataFrame([signal.to_dict() for signal in signals])
    if signals:
        tick_rows_df = run_tick_replay_batch(
            [signal.to_dict() for signal in signals],
            ticks_dir=ticks_dir,
            jobs=jobs,
            slippage_mode=params.slippage_mode,
            fixed_slippage_pips=params.fixed_slippage_pips,
            entry_delay_seconds=params.entry_delay_seconds,
        )
    else:
        tick_rows_df = pd.DataFrame()

    minute_trade_df = _minute_trade_frame(
        comparison_label=comparison_label,
        filter_label=filter_label,
        minute_result=minute_result,
    )
    if tick_rows_df.empty or "pnl_pips" not in tick_rows_df.columns:
        tick_trade_df = pd.DataFrame(columns=["comparison_label", "year", "pnl_pips"])
    else:
        tick_trade_df = tick_rows_df.loc[pd.to_numeric(tick_rows_df["pnl_pips"], errors="coerce").notna()].copy()

    comparison_trades_df = _build_trade_comparison(signals_df=signals_df, tick_df=tick_rows_df)
    summary_df = build_e004_summary(
        [
            _summary_row(
                comparison_label=comparison_label,
                params=params,
                eligible_days_by_segment=eligible_days_by_segment,
                signals_df=signals_df,
                tick_trade_df=tick_trade_df,
                minute_trade_df=minute_trade_df,
                tick_rows=tick_rows_df,
            )
        ]
    )
    split_df = _merge_segment_summary(
        tick_df=tick_trade_df,
        minute_df=minute_trade_df,
        eligible_days_by_segment=eligible_days_by_segment,
    )
    year_df = _merge_year_summary(tick_df=tick_trade_df, minute_df=minute_trade_df)
    sanity_df = _aggregate_tick_sanity(
        comparison_label=comparison_label,
        params=params,
        tick_rows=tick_rows_df,
        minute_sanity=minute_result.sanity,
        load_summary=load_summary,
    )

    metadata = {
        "experiment_code": params.experiment_code,
        "variant_code": params.variant_code,
        "slot_id": params.slot_id,
        "side": params.side,
        "comparison_label": comparison_label,
        "pass_stability_gate": params.pass_stability_gate,
        "allow_gate_fail": allow_gate_fail,
        "dataset_dir": str(dataset_dir),
        "ticks_dir": str(ticks_dir),
        "years": years,
        "jobs": int(jobs),
        "date_from": params.date_from,
        "date_to": params.date_to,
        "eligible_days_by_segment": eligible_days_by_segment,
        "load_summary": asdict(load_summary),
        "signal_day_count": int(len(signals_df)),
        "tick_trade_count": int(len(tick_trade_df)),
        "minute_trade_count": int(len(minute_trade_df)),
        "notes": params.notes,
    }

    write_json(paths["metadata_json"], metadata)
    write_json(paths["params_json"], params.to_dict())
    signals_df.to_csv(paths["signal_days_csv"], index=False)
    summary_df.to_csv(paths["summary_csv"], index=False)
    split_df.to_csv(paths["split_summary_csv"], index=False)
    year_df.to_csv(paths["year_summary_csv"], index=False)
    comparison_trades_df.to_csv(paths["trades_csv"], index=False)
    sanity_df.to_csv(paths["sanity_csv"], index=False)

    return {
        "signal_days_df": signals_df,
        "summary_df": summary_df,
        "split_df": split_df,
        "year_df": year_df,
        "trades_df": comparison_trades_df,
        "sanity_df": sanity_df,
    }
