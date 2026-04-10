from __future__ import annotations

import math

import pandas as pd


DEFAULT_IN_YEARS = (2019, 2020, 2021, 2022)
DEFAULT_OUT_YEARS = (2023, 2024, 2025)
DEFAULT_STABILITY_RANK_GAP_MAX = 100


def _safe_profit_factor(values: pd.Series) -> float:
    gains = float(values[values > 0.0].sum())
    losses = float(-values[values < 0.0].sum())
    if losses == 0.0:
        return math.inf if gains > 0.0 else math.nan
    return gains / losses


def _safe_max_dd(values: pd.Series) -> float:
    if values.empty:
        return math.nan
    equity = values.cumsum()
    dd = equity - equity.cummax()
    return float(dd.min())


def build_e001_summary(summary_rows: list[dict[str, object]]) -> pd.DataFrame:
    columns = [
        "comparison_label",
        "comparison_family",
        "filter_label",
        "pre_range_threshold",
        "resolved_threshold",
        "input_pass_stability_gate",
        "trade_count",
        "eligible_day_count",
        "gross_pips",
        "in_gross_pips",
        "out_gross_pips",
        "rank_in",
        "rank_out",
        "rank_gap_abs",
        "top1_share_of_total",
        "ex_top10_gross_pips",
        "pass_stability_gate",
        "mean_pips",
        "median_pips",
        "std_pips",
        "win_rate",
        "profit_factor",
        "max_dd_pips",
        "annualized_pips",
    ]
    if not summary_rows:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(summary_rows)
    df["rank_in"] = df["in_gross_pips"].rank(ascending=False, method="min")
    df["rank_out"] = df["out_gross_pips"].rank(ascending=False, method="min")
    df["rank_gap_abs"] = (df["rank_in"] - df["rank_out"]).abs()
    df["pass_stability_gate"] = (
        (df["in_gross_pips"] > 0.0)
        & (df["out_gross_pips"] > 0.0)
        & (df["rank_gap_abs"] < DEFAULT_STABILITY_RANK_GAP_MAX)
        & (df["ex_top10_gross_pips"] > 0.0)
    )
    return df.loc[:, [column for column in columns if column in df.columns]]


def build_e002_summary(summary_rows: list[dict[str, object]]) -> pd.DataFrame:
    columns = [
        "comparison_label",
        "filter_label",
        "tp_pips",
        "sl_pips",
        "input_pass_stability_gate",
        "trade_count",
        "eligible_day_count",
        "gross_pips",
        "in_gross_pips",
        "out_gross_pips",
        "rank_in",
        "rank_out",
        "rank_gap_abs",
        "top1_share_of_total",
        "ex_top10_gross_pips",
        "pass_stability_gate",
        "mean_pips",
        "median_pips",
        "std_pips",
        "win_rate",
        "profit_factor",
        "max_dd_pips",
        "annualized_pips",
    ]
    if not summary_rows:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(summary_rows)
    df["rank_in"] = df["in_gross_pips"].rank(ascending=False, method="min")
    df["rank_out"] = df["out_gross_pips"].rank(ascending=False, method="min")
    df["rank_gap_abs"] = (df["rank_in"] - df["rank_out"]).abs()
    df["pass_stability_gate"] = (
        (df["in_gross_pips"] > 0.0)
        & (df["out_gross_pips"] > 0.0)
        & (df["rank_gap_abs"] < DEFAULT_STABILITY_RANK_GAP_MAX)
        & (df["ex_top10_gross_pips"] > 0.0)
    )
    return df.loc[:, [column for column in columns if column in df.columns]]


def build_e003_summary(summary_rows: list[dict[str, object]]) -> pd.DataFrame:
    columns = [
        "comparison_label",
        "filter_label",
        "tp_pips",
        "sl_pips",
        "forced_exit_clock_local",
        "input_pass_stability_gate",
        "trade_count",
        "eligible_day_count",
        "gross_pips",
        "in_gross_pips",
        "out_gross_pips",
        "rank_in",
        "rank_out",
        "rank_gap_abs",
        "top1_share_of_total",
        "ex_top10_gross_pips",
        "pass_stability_gate",
        "mean_pips",
        "median_pips",
        "std_pips",
        "win_rate",
        "profit_factor",
        "max_dd_pips",
        "annualized_pips",
    ]
    if not summary_rows:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(summary_rows)
    df["rank_in"] = df["in_gross_pips"].rank(ascending=False, method="min")
    df["rank_out"] = df["out_gross_pips"].rank(ascending=False, method="min")
    df["rank_gap_abs"] = (df["rank_in"] - df["rank_out"]).abs()
    df["pass_stability_gate"] = (
        (df["in_gross_pips"] > 0.0)
        & (df["out_gross_pips"] > 0.0)
        & (df["rank_gap_abs"] < DEFAULT_STABILITY_RANK_GAP_MAX)
        & (df["ex_top10_gross_pips"] > 0.0)
    )
    return df.loc[:, [column for column in columns if column in df.columns]]


def build_e004_summary(summary_rows: list[dict[str, object]]) -> pd.DataFrame:
    columns = [
        "comparison_label",
        "filter_label",
        "tp_pips",
        "sl_pips",
        "forced_exit_clock_local",
        "slippage_mode",
        "fixed_slippage_pips",
        "entry_delay_seconds",
        "input_pass_stability_gate",
        "eligible_day_count",
        "signal_day_count",
        "trade_count",
        "minute_trade_count",
        "gross_pips",
        "minute_gross_pips",
        "delta_gross_pips",
        "in_gross_pips",
        "out_gross_pips",
        "minute_in_gross_pips",
        "minute_out_gross_pips",
        "win_rate",
        "minute_win_rate",
        "profit_factor",
        "minute_profit_factor",
        "max_dd_pips",
        "minute_max_dd_pips",
        "annualized_pips",
        "minute_annualized_pips",
        "pass_stability_gate",
        "tick_not_found_count",
        "forced_exit_missing_count",
        "entry_after_forced_exit_count",
    ]
    if not summary_rows:
        return pd.DataFrame(columns=columns)
    df = pd.DataFrame(summary_rows)
    return df.loc[:, [column for column in columns if column in df.columns]]


def build_split_summary(
    trades_df: pd.DataFrame,
    *,
    eligible_days_by_segment: dict[str, int],
) -> pd.DataFrame:
    columns = [
        "comparison_label",
        "segment",
        "eligible_day_count",
        "trade_count",
        "gross_pips",
        "mean_pips",
        "win_rate",
        "profit_factor",
        "max_dd_pips",
    ]
    if trades_df.empty:
        return pd.DataFrame(columns=columns)

    segment_defs = {
        "in": DEFAULT_IN_YEARS,
        "out": DEFAULT_OUT_YEARS,
        "full": DEFAULT_IN_YEARS + DEFAULT_OUT_YEARS,
    }
    rows: list[dict[str, object]] = []
    for comparison_label, group in trades_df.groupby("comparison_label", sort=False):
        for segment, years in segment_defs.items():
            segment_group = group[group["year"].isin(years)].copy()
            pnl = segment_group["pnl_pips"] if not segment_group.empty else pd.Series(dtype=float)
            rows.append(
                {
                    "comparison_label": comparison_label,
                    "segment": segment,
                    "eligible_day_count": int(eligible_days_by_segment.get(segment, 0)),
                    "trade_count": int(len(segment_group)),
                    "gross_pips": float(pnl.sum()) if not pnl.empty else 0.0,
                    "mean_pips": float(pnl.mean()) if not pnl.empty else math.nan,
                    "win_rate": float((pnl > 0.0).mean()) if not pnl.empty else math.nan,
                    "profit_factor": float(_safe_profit_factor(pnl)),
                    "max_dd_pips": float(_safe_max_dd(pnl)),
                }
            )
    return pd.DataFrame(rows, columns=columns)


def build_year_summary(trades_df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "comparison_label",
        "year",
        "trade_count",
        "gross_pips",
        "mean_pips",
        "median_pips",
        "std_pips",
        "win_rate",
        "profit_factor",
        "max_dd_pips",
    ]
    if trades_df.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, object]] = []
    for (comparison_label, year), group in trades_df.groupby(["comparison_label", "year"], sort=True):
        pnl = group["pnl_pips"]
        rows.append(
            {
                "comparison_label": comparison_label,
                "year": int(year),
                "trade_count": int(len(group)),
                "gross_pips": float(pnl.sum()),
                "mean_pips": float(pnl.mean()) if not pnl.empty else math.nan,
                "median_pips": float(pnl.median()) if not pnl.empty else math.nan,
                "std_pips": float(pnl.std(ddof=0)) if not pnl.empty else math.nan,
                "win_rate": float((pnl > 0.0).mean()) if not pnl.empty else math.nan,
                "profit_factor": float(_safe_profit_factor(pnl)),
                "max_dd_pips": float(_safe_max_dd(pnl)),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def build_sanity_summary(sanity_rows: list[dict[str, object]]) -> pd.DataFrame:
    if not sanity_rows:
        return pd.DataFrame()
    return pd.DataFrame(sanity_rows)
