from __future__ import annotations

from dataclasses import asdict
import math
from pathlib import Path
from typing import Any

import pandas as pd

from timer_entry.backtest_1m import run_backtest_1m
from timer_entry.features import compute_feature_row
from timer_entry.filters import parse_volatility_filter_label
from timer_entry.minute_data import MinuteDataSummary, TradingDay, load_trading_days

from .io import ensure_run_layout, write_json
from .params import E001Params
from .reporting import (
    DEFAULT_IN_YEARS,
    DEFAULT_OUT_YEARS,
    build_e001_summary,
    build_sanity_summary,
    build_split_summary,
    build_year_summary,
)


def _clock_columns(market_tz: str) -> tuple[str, str]:
    if market_tz == "Asia/Tokyo":
        return "Clock_JST", "Minute_JST"
    return "Clock_London", "Minute_London"


def _row_at(day: TradingDay, clock_hhmm: str) -> pd.Series | None:
    clock_col, _ = _clock_columns(day.session_tz)
    if clock_hhmm in day.frame.index:
        row = day.frame.loc[clock_hhmm]
        if isinstance(row, pd.DataFrame):
            return row.iloc[0]
        return row
    matches = day.frame.loc[day.frame[clock_col] == clock_hhmm]
    if matches.empty:
        return None
    return matches.iloc[0]


def _filter_days(days: list[TradingDay], *, date_from: str | None, date_to: str | None) -> list[TradingDay]:
    filtered = days
    if date_from is not None:
        filtered = [day for day in filtered if day.session_date >= date_from]
    if date_to is not None:
        filtered = [day for day in filtered if day.session_date <= date_to]
    return filtered


def _eligible_feature_rows(days: list[TradingDay], params: E001Params) -> list[dict[str, object]]:
    _, minute_col = _clock_columns(params.market_tz)
    rows: list[dict[str, object]] = []
    for day in days:
        if day.session_tz != params.market_tz:
            continue
        entry_row = _row_at(day, params.baseline.entry_clock_local)
        forced_row = _row_at(day, params.baseline.forced_exit_clock_local)
        if entry_row is None or forced_row is None:
            continue
        entry_time = pd.Timestamp(entry_row[minute_col])
        forced_time = pd.Timestamp(forced_row[minute_col])
        if forced_time <= entry_time:
            continue
        feature_result = compute_feature_row(day.frame, entry_time=entry_time)
        if not feature_result.feature_available:
            continue
        rows.append(
            {
                "session_date": day.session_date,
                "year": int(day.year),
                "pre_open_slope_pips": float(feature_result.pre_open_slope_pips),
                "pre_range_pips": float(feature_result.pre_range_pips),
                "trend_ratio": float(feature_result.trend_ratio) if not math.isnan(feature_result.trend_ratio) else math.nan,
            }
        )
    return rows


def _eligible_days_by_segment(feature_rows: list[dict[str, object]]) -> dict[str, int]:
    if not feature_rows:
        return {"in": 0, "out": 0, "full": 0}
    feature_df = pd.DataFrame(feature_rows)
    return {
        "in": int(feature_df["year"].isin(DEFAULT_IN_YEARS).sum()),
        "out": int(feature_df["year"].isin(DEFAULT_OUT_YEARS).sum()),
        "full": int(len(feature_df)),
    }


def _resolve_pre_range_thresholds(
    comparison_labels: tuple[str, ...],
    feature_rows: list[dict[str, object]],
) -> dict[str, float]:
    thresholds: dict[str, float] = {}
    if not feature_rows:
        return thresholds
    feature_df = pd.DataFrame(feature_rows)
    values = pd.to_numeric(feature_df["pre_range_pips"], errors="coerce").dropna()
    if values.empty:
        return thresholds

    for label in comparison_labels:
        vol_spec = parse_volatility_filter_label(label)
        if vol_spec is None:
            continue
        _, raw_threshold = vol_spec
        if raw_threshold == "med":
            thresholds[label] = float(values.median())
        else:
            thresholds[label] = float(values.quantile(float(raw_threshold) / 100.0))
    return thresholds


def _comparison_trade_frame(
    *,
    comparison_label: str,
    comparison_family: str,
    pre_range_threshold: float | None,
    result: Any,
) -> pd.DataFrame:
    rows = []
    for trade in result.trades:
        row = trade.to_dict()
        row["comparison_label"] = comparison_label
        row["comparison_family"] = comparison_family
        row["filter_label"] = comparison_label
        row["pre_range_threshold"] = pre_range_threshold
        row["year"] = int(str(trade.date_local)[:4])
        rows.append(row)
    return pd.DataFrame(rows)


def _comparison_summary_row(
    *,
    comparison_label: str,
    comparison_family: str,
    pre_range_threshold: float | None,
    input_pass_stability_gate: bool,
    result: Any,
) -> dict[str, object]:
    trades = pd.DataFrame([trade.to_dict() for trade in result.trades])
    if trades.empty:
        pnl = pd.Series(dtype=float)
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

    summary = result.summary.to_dict()
    summary.update(
        {
            "comparison_label": comparison_label,
            "comparison_family": comparison_family,
            "filter_label": comparison_label,
            "pre_range_threshold": pre_range_threshold,
            "input_pass_stability_gate": input_pass_stability_gate,
            "in_gross_pips": round(in_gross_pips, 6),
            "out_gross_pips": round(out_gross_pips, 6),
            "top1_share_of_total": top1_share_of_total,
            "ex_top10_gross_pips": round(ex_top10_gross_pips, 6),
        }
    )
    return summary


def run_e001(
    *,
    params: E001Params,
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
    feature_rows = _eligible_feature_rows(filtered_days, params)
    eligible_days_by_segment = _eligible_days_by_segment(feature_rows)
    pre_range_thresholds = _resolve_pre_range_thresholds(params.comparison_labels, feature_rows)

    all_trade_frames: list[pd.DataFrame] = []
    summary_rows: list[dict[str, object]] = []
    sanity_rows: list[dict[str, object]] = []

    for comparison_label in params.comparison_labels:
        pre_range_threshold = pre_range_thresholds.get(comparison_label)
        setting = params.to_strategy_setting(
            comparison_label=comparison_label,
            pre_range_threshold=pre_range_threshold,
        )
        result = run_backtest_1m(
            filtered_days,
            setting,
            time_jst_fallback_count=load_summary.time_jst_fallback_count,
            duplicate_clock_removed_count=load_summary.duplicate_clock_removed_count,
        )
        all_trade_frames.append(
            _comparison_trade_frame(
                comparison_label=comparison_label,
                comparison_family=params.comparison_family,
                pre_range_threshold=pre_range_threshold,
                result=result,
            )
        )
        summary_rows.append(
            _comparison_summary_row(
                comparison_label=comparison_label,
                comparison_family=params.comparison_family,
                pre_range_threshold=pre_range_threshold,
                input_pass_stability_gate=params.pass_stability_gate,
                result=result,
            )
        )
        sanity_row = result.sanity.to_dict()
        sanity_row["comparison_label"] = comparison_label
        sanity_row["comparison_family"] = params.comparison_family
        sanity_row["pre_range_threshold"] = pre_range_threshold
        sanity_rows.append(sanity_row)

    trades_df = pd.concat(all_trade_frames, ignore_index=True) if all_trade_frames else pd.DataFrame()
    summary_df = build_e001_summary(summary_rows)
    split_df = build_split_summary(trades_df, eligible_days_by_segment=eligible_days_by_segment)
    year_df = build_year_summary(trades_df)
    sanity_df = build_sanity_summary(sanity_rows)

    metadata = {
        "experiment_code": params.experiment_code,
        "variant_code": params.variant_code,
        "slot_id": params.slot_id,
        "side": params.side,
        "comparison_family": params.comparison_family,
        "comparison_labels": list(params.comparison_labels),
        "pass_stability_gate": params.pass_stability_gate,
        "allow_gate_fail": allow_gate_fail,
        "dataset_dir": str(dataset_dir),
        "years": years,
        "date_from": params.date_from,
        "date_to": params.date_to,
        "eligible_days_by_segment": eligible_days_by_segment,
        "pre_range_thresholds": pre_range_thresholds,
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
