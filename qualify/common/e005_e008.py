from __future__ import annotations

from dataclasses import asdict
import math
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from timer_entry.minute_data import load_trading_days

from .e001 import _baseline_threshold_context, _eligible_days_by_segment, _eligible_feature_rows, _filter_days
from .e001 import _concat_trade_frames
from .e004 import _aggregate_tick_sanity
from .io import ensure_run_layout, write_json
from .params import E004Params, E005E008Params
from .reporting import DEFAULT_OUT_YEARS, build_sanity_summary, build_split_summary, build_year_summary

DEFAULT_WALKFORWARD_TEST_YEARS = tuple(range(2021, 2026))
from .tick_replay import generate_e004_signal_days, run_tick_replay_batch


def parse_output_aliases(values: list[str] | tuple[str, ...] | None) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            raise ValueError(f"output alias must use FROM=TO format: {value}")
        source, target = (part.strip().upper() for part in value.split("=", 1))
        if source not in {"E005", "E006", "E007", "E008"}:
            raise ValueError(f"Unsupported output alias source: {source}")
        if not target:
            raise ValueError(f"Output alias target must not be empty: {value}")
        aliases[source] = target
    return aliases


def _annualized_pips(trades_df: pd.DataFrame) -> float:
    if trades_df.empty:
        return math.nan
    year_count = len(sorted(set(pd.to_numeric(trades_df["year"], errors="coerce").dropna().astype(int))))
    if year_count == 0:
        return math.nan
    return float(pd.to_numeric(trades_df["pnl_pips"], errors="coerce").fillna(0.0).sum()) / year_count


def _safe_profit_factor(values: pd.Series) -> float:
    valid = pd.to_numeric(values, errors="coerce").dropna()
    if valid.empty:
        return math.nan
    gains = float(valid[valid > 0.0].sum())
    losses = float(-valid[valid < 0.0].sum())
    if losses == 0.0:
        return math.inf if gains > 0.0 else math.nan
    return gains / losses


def _safe_max_dd(values: pd.Series) -> float:
    valid = pd.to_numeric(values, errors="coerce").dropna()
    if valid.empty:
        return math.nan
    equity = valid.cumsum()
    dd = equity - equity.cummax()
    return float(dd.min())


def _base_tick_trades(tick_rows_df: pd.DataFrame) -> pd.DataFrame:
    if tick_rows_df.empty or "pnl_pips" not in tick_rows_df.columns:
        return pd.DataFrame(columns=["comparison_label", "year", "pnl_pips"])
    return tick_rows_df.loc[pd.to_numeric(tick_rows_df["pnl_pips"], errors="coerce").notna()].copy()


def _variant_metrics(
    *,
    variant_df: pd.DataFrame,
    baseline_key: object,
    variant_col: str,
    metric_cols: tuple[str, ...],
) -> pd.DataFrame:
    if variant_df.empty:
        return variant_df
    out = variant_df.copy()
    baseline = out.loc[out[variant_col] == baseline_key]
    if baseline.empty:
        for metric_col in metric_cols:
            out[f"{metric_col}_degradation_vs_{baseline_key}"] = pd.NA
        return out
    baseline_row = baseline.iloc[0]
    for metric_col in metric_cols:
        degr_col = f"{metric_col}_degradation_vs_{baseline_key}"
        base_value = baseline_row.get(metric_col)
        if pd.isna(base_value) or float(base_value) == 0.0:
            out[degr_col] = pd.NA
        else:
            out[degr_col] = pd.to_numeric(out[metric_col], errors="coerce") / float(base_value) - 1.0
    return out


def _variant_summary_row(
    *,
    trades_df: pd.DataFrame,
    eligible_days_by_segment: dict[str, int],
    variant_col: str,
    variant_value: object,
) -> dict[str, object]:
    out_trades = trades_df.loc[trades_df["year"].isin(DEFAULT_OUT_YEARS)].copy() if not trades_df.empty else pd.DataFrame()
    pnl = pd.to_numeric(out_trades["pnl_pips"], errors="coerce") if not out_trades.empty else pd.Series(dtype=float)
    return {
        variant_col: variant_value,
        "eligible_day_count": int(eligible_days_by_segment["out"]),
        "trade_count": int(len(out_trades)),
        "gross_pips": float(pnl.sum()) if not pnl.empty else 0.0,
        "mean_pips": float(pnl.mean()) if not pnl.empty else math.nan,
        "win_rate": float((pnl > 0.0).mean()) if not pnl.empty else math.nan,
        "profit_factor": float(_safe_profit_factor(pnl)),
        "max_dd_pips": float(_safe_max_dd(pnl)),
        "annualized_pips": _annualized_pips(out_trades),
    }


def _variant_sanity_row(
    *,
    tick_rows_df: pd.DataFrame,
    variant_col: str,
    variant_value: object,
) -> dict[str, object]:
    valid = tick_rows_df.fillna(False) if not tick_rows_df.empty else pd.DataFrame()
    return {
        variant_col: variant_value,
        "trade_row_count": int(len(tick_rows_df)),
        "tick_trade_count": int(len(_base_tick_trades(tick_rows_df))),
        "entry_equals_exit_count": int(valid["entry_equals_exit_all_flag"].sum()) if not valid.empty else 0,
        "entry_equals_exit_sl_count": int(valid["entry_equals_exit_sl_flag"].sum()) if not valid.empty else 0,
        "same_tick_conflict_count": int(valid["tp_sl_same_tick_flag"].sum()) if not valid.empty else 0,
        "forced_exit_missing_count": int(valid["forced_exit_missing_flag"].sum()) if not valid.empty else 0,
        "tick_not_found_count": int(valid["tick_not_found_flag"].sum()) if not valid.empty else 0,
        "entry_after_forced_exit_count": int(valid["entry_after_forced_exit_flag"].sum()) if not valid.empty else 0,
    }


def _build_walkforward_summary(trades_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    valid = trades_df.loc[pd.to_numeric(trades_df["pnl_pips"], errors="coerce").notna()].copy() if not trades_df.empty else trades_df.copy()
    valid["year"] = pd.to_numeric(valid["year"], errors="coerce")
    # E006 is a yearly out-sample stress summary; it does not re-optimize on train_years.
    for test_year in DEFAULT_WALKFORWARD_TEST_YEARS:
        train_years = (test_year - 2, test_year - 1)
        test_trades = valid.loc[valid["year"] == test_year].copy()
        pnl = pd.to_numeric(test_trades["pnl_pips"], errors="coerce") if not test_trades.empty else pd.Series(dtype=float)
        gross = float(pnl.sum()) if not pnl.empty else 0.0
        loss_streak = 0
        if not pnl.empty:
            current = 0
            for is_loss in (pnl < 0.0).tolist():
                current = current + 1 if is_loss else 0
                loss_streak = max(loss_streak, current)
        rows.append(
            {
                "train_years": f"{train_years[0]}-{train_years[1]}",
                "test_year": test_year,
                "trade_count": int(len(test_trades)),
                "out_pnl": gross,
                "pf": float(_safe_profit_factor(pnl)),
                "max_dd_pips": float(_safe_max_dd(pnl)),
                "continuous_loss_period": int(loss_streak),
                "win_rate": float((pnl > 0.0).mean()) if not pnl.empty else math.nan,
                "annualized_pips": gross,
            }
        )
    return pd.DataFrame(rows)


def _pips_year_rate_pct_at_150usd(target_maintenance_margin_pct: float) -> float:
    if target_maintenance_margin_pct <= 0.0:
        return math.nan
    return 166.67 / float(target_maintenance_margin_pct)


def _build_target_maintenance_margin_outputs(
    *,
    trades_df: pd.DataFrame,
    initial_capital_jpy: float,
    target_maintenance_margin_pct: float,
    kill_switch_dd_pct: float,
    sl_pips: float,
    eligible_day_count: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    valid = trades_df.loc[pd.to_numeric(trades_df["pnl_pips"], errors="coerce").notna()].copy()
    if valid.empty:
        summary = pd.DataFrame(
            [
                {
                    "target_maintenance_margin_pct": target_maintenance_margin_pct,
                    "initial_capital_jpy": initial_capital_jpy,
                    "kill_switch_dd_pct": kill_switch_dd_pct,
                    "sl_pips": sl_pips,
                    "trades_processed": 0,
                    "trade_rate": 0.0,
                    "win_rate": math.nan,
                    "annualized_pips": math.nan,
                    "final_equity_jpy": initial_capital_jpy,
                    "total_return_pct": 0.0,
                    "cagr": 0.0,
                    "max_dd_pct": 0.0,
                    "min_maintenance_margin_pct": math.inf,
                    "maintenance_below_130_count": 0,
                    "maintenance_below_100_count": 0,
                    "equity_negative_count": 0,
                    "stop_triggered": False,
                    "pips_year_rate_pct_at_150usd": _pips_year_rate_pct_at_150usd(
                        float(target_maintenance_margin_pct)
                    ),
                    "needs_higher_maintenance_margin": False,
                    "rejection_reason": "",
                }
            ]
        )
        return pd.DataFrame(), summary

    sort_col = "exit_time" if "exit_time" in valid.columns else "entry_time"
    valid = valid.sort_values(sort_col).reset_index(drop=True)

    equity = float(initial_capital_jpy)
    peak = float(initial_capital_jpy)
    halted = False
    rows: list[dict[str, object]] = []

    for _, trade in valid.iterrows():
        if halted:
            break
        equity_before = equity
        entry_price = float(trade["entry_price"])
        margin_rate = 0.04
        required_margin_per_unit_jpy = entry_price * margin_rate
        units = (
            equity_before * 100.0 / (float(target_maintenance_margin_pct) * required_margin_per_unit_jpy)
            if target_maintenance_margin_pct > 0.0 and required_margin_per_unit_jpy > 0.0
            else 0.0
        )
        required_margin_jpy = units * entry_price * 0.04
        entry_maintenance_margin_pct = equity_before / required_margin_jpy * 100.0 if required_margin_jpy > 0.0 else math.inf
        expected_loss_at_sl_jpy = units * float(sl_pips) * 0.01
        equity_at_sl_jpy = equity_before - expected_loss_at_sl_jpy
        maintenance_margin_pct = equity_at_sl_jpy / required_margin_jpy * 100.0 if required_margin_jpy > 0.0 else math.inf
        pnl_pips = float(trade["pnl_pips"])
        pnl_jpy = units * pnl_pips * 0.01
        equity += pnl_jpy
        peak = max(peak, equity)
        dd_pct = equity / peak - 1.0 if peak > 0.0 else 0.0
        kill_switch_triggered = dd_pct <= float(kill_switch_dd_pct)
        rows.append(
            {
                "date_local": trade["date_local"],
                "year": int(trade["year"]),
                "entry_time": trade["entry_time"],
                "exit_time": trade["exit_time"],
                "entry_price": entry_price,
                "pnl_pips": pnl_pips,
                "equity_before_jpy": equity_before,
                "target_maintenance_margin_pct": float(target_maintenance_margin_pct),
                "sl_pips": float(sl_pips),
                "pip_value_jpy_per_unit": 0.01,
                "units": units,
                "expected_loss_at_sl_jpy": expected_loss_at_sl_jpy,
                "required_margin_jpy": required_margin_jpy,
                "entry_maintenance_margin_pct": entry_maintenance_margin_pct,
                "equity_at_sl_jpy": equity_at_sl_jpy,
                "maintenance_margin_pct": maintenance_margin_pct,
                "pnl_jpy": pnl_jpy,
                "equity_jpy": equity,
                "drawdown_pct": dd_pct,
                "kill_switch_triggered": kill_switch_triggered,
            }
        )
        if kill_switch_triggered:
            halted = True

    equity_df = pd.DataFrame(rows)
    trade_count = int(len(equity_df))
    year_count = max(1, len(sorted(set(equity_df["year"].astype(int))))) if not equity_df.empty else 1
    final_equity = float(equity_df["equity_jpy"].iloc[-1]) if not equity_df.empty else float(initial_capital_jpy)
    total_return = final_equity / float(initial_capital_jpy) - 1.0 if initial_capital_jpy > 0.0 else 0.0
    cagr = (final_equity / float(initial_capital_jpy)) ** (1.0 / year_count) - 1.0 if final_equity > 0.0 and initial_capital_jpy > 0.0 else -1.0
    maintenance_series = pd.to_numeric(equity_df["maintenance_margin_pct"], errors="coerce")
    maintenance_below_130_count = int((maintenance_series < 130.0).sum()) if not equity_df.empty else 0
    maintenance_below_100_count = int((maintenance_series < 100.0).sum()) if not equity_df.empty else 0
    stop_triggered = bool(equity_df["kill_switch_triggered"].any()) if not equity_df.empty else False
    if maintenance_below_100_count > 0:
        rejection_reason = "maintenance_below_100"
    elif stop_triggered:
        rejection_reason = "stop_triggered"
    elif maintenance_below_130_count > 0:
        rejection_reason = "maintenance_below_130"
    else:
        rejection_reason = ""
    summary = pd.DataFrame(
        [
            {
                "target_maintenance_margin_pct": float(target_maintenance_margin_pct),
                "initial_capital_jpy": float(initial_capital_jpy),
                "kill_switch_dd_pct": float(kill_switch_dd_pct),
                "sl_pips": float(sl_pips),
                "trades_processed": trade_count,
                "trade_rate": trade_count / float(eligible_day_count) if eligible_day_count > 0 else math.nan,
                "win_rate": float((pd.to_numeric(equity_df["pnl_pips"], errors="coerce") > 0.0).mean()) if not equity_df.empty else math.nan,
                "annualized_pips": float(pd.to_numeric(equity_df["pnl_pips"], errors="coerce").sum()) / year_count if trade_count > 0 else math.nan,
                "final_equity_jpy": final_equity,
                "total_return_pct": total_return,
                "cagr": cagr,
                "max_dd_pct": float(pd.to_numeric(equity_df["drawdown_pct"], errors="coerce").min()) if not equity_df.empty else 0.0,
                "min_maintenance_margin_pct": float(maintenance_series.min()) if not equity_df.empty else math.inf,
                "maintenance_below_130_count": maintenance_below_130_count,
                "maintenance_below_100_count": maintenance_below_100_count,
                "equity_negative_count": int((pd.to_numeric(equity_df["equity_jpy"], errors="coerce") < 0.0).sum()) if not equity_df.empty else 0,
                "stop_triggered": stop_triggered,
                "pips_year_rate_pct_at_150usd": _pips_year_rate_pct_at_150usd(float(target_maintenance_margin_pct)),
                "needs_higher_maintenance_margin": bool(stop_triggered or maintenance_below_130_count > 0),
                "rejection_reason": rejection_reason,
            }
        ]
    )
    return equity_df, summary


def _prepare_e004_baseline(
    *,
    params: E004Params,
    dataset_dir: str | Path,
    ticks_dir: str | Path,
    years: list[int],
    jobs: int,
) -> dict[str, object]:
    print(f"[LOAD] minute dataset from {dataset_dir}")
    days, load_summary = load_trading_days(
        years,
        dataset_dir=dataset_dir,
        session_tz=params.market_tz,  # type: ignore[arg-type]
        exclude_windows=params.baseline.exclude_windows,
    )
    filtered_days = _filter_days(days, date_from=params.date_from, date_to=params.date_to)
    feature_rows = _eligible_feature_rows(filtered_days, params)  # type: ignore[arg-type]
    eligible_days_by_segment = _eligible_days_by_segment(feature_rows)
    pre_range_threshold, dynamic_filter_threshold, threshold_metadata = _baseline_threshold_context(
        params.baseline.filter_labels,
        feature_rows,
    )

    print(f"[SIGNALS] building E004 baseline from {len(filtered_days)} filtered days")
    signals, minute_result = generate_e004_signal_days(
        filtered_days,
        params=params,
        load_summary=load_summary,
        pre_range_threshold=pre_range_threshold,
        dynamic_filter_threshold=dynamic_filter_threshold,
    )
    signals_df = pd.DataFrame([signal.to_dict() for signal in signals])
    print(f"[SIGNALS] baseline signal days={len(signals_df)}")

    if signals:
        print(
            f"[TICK] baseline replay start ticks_dir={ticks_dir} jobs={jobs} "
            f"slippage={params.fixed_slippage_pips} delay={params.entry_delay_seconds}s"
        )
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

    return {
        "load_summary": load_summary,
        "minute_result": minute_result,
        "signals": signals,
        "signals_df": signals_df,
        "tick_rows_df": tick_rows_df,
        "tick_trades_df": _base_tick_trades(tick_rows_df),
        "eligible_days_by_segment": eligible_days_by_segment,
        "pre_range_threshold": pre_range_threshold,
        "dynamic_filter_threshold": dynamic_filter_threshold,
        "threshold_metadata": threshold_metadata,
    }


def _run_e005(
    *,
    params: E004Params,
    ticks_dir: str | Path,
    jobs: int,
    root_out_dir: str | Path,
    baseline: dict[str, object],
    slippage_values: tuple[float, ...],
    output_code: str = "E005",
) -> dict[str, pd.DataFrame]:
    paths = ensure_run_layout(Path(root_out_dir) / output_code)
    signal_rows = [signal.to_dict() for signal in baseline["signals"]]  # type: ignore[index]
    eligible_days_by_segment = baseline["eligible_days_by_segment"]  # type: ignore[index]

    summary_rows: list[dict[str, object]] = []
    year_frames: list[pd.DataFrame] = []
    split_frames: list[pd.DataFrame] = []
    sanity_rows: list[dict[str, object]] = []
    trade_frames: list[pd.DataFrame] = []

    for slip in tqdm(slippage_values, desc="E005 slippage sweep", unit="grid", mininterval=0.5):
        tick_rows_df = run_tick_replay_batch(
            signal_rows,
            ticks_dir=ticks_dir,
            jobs=jobs,
            slippage_mode="fixed",
            fixed_slippage_pips=float(slip),
            entry_delay_seconds=params.entry_delay_seconds,
        )
        tick_trades_df = _base_tick_trades(tick_rows_df)
        summary_rows.append(
            {
                **_variant_summary_row(
                    trades_df=tick_trades_df,
                    eligible_days_by_segment=eligible_days_by_segment,  # type: ignore[arg-type]
                    variant_col="slip_pips",
                    variant_value=float(slip),
                ),
                "round_trip_slip_pips": float(slip) * 2.0,
                "entry_delay_seconds": int(params.entry_delay_seconds),
            }
        )
        year_frame = build_year_summary(tick_trades_df)
        if not year_frame.empty:
            year_frame["slip_pips"] = float(slip)
            year_frame["round_trip_slip_pips"] = float(slip) * 2.0
            year_frames.append(year_frame)
        split_frame = build_split_summary(
            tick_trades_df,
            eligible_days_by_segment=eligible_days_by_segment,  # type: ignore[arg-type]
        )
        if not split_frame.empty:
            split_frame["slip_pips"] = float(slip)
            split_frame["round_trip_slip_pips"] = float(slip) * 2.0
            split_frames.append(split_frame)
        sanity_rows.append(
            {
                **_variant_sanity_row(tick_rows_df=tick_rows_df, variant_col="slip_pips", variant_value=float(slip)),
                "round_trip_slip_pips": float(slip) * 2.0,
            }
        )
        if not tick_rows_df.empty:
            trade_frame = tick_rows_df.copy()
            trade_frame["slip_pips"] = float(slip)
            trade_frame["round_trip_slip_pips"] = float(slip) * 2.0
            trade_frames.append(trade_frame)

    summary_df = _variant_metrics(
        variant_df=pd.DataFrame(summary_rows),
        baseline_key=0.0,
        variant_col="slip_pips",
        metric_cols=("gross_pips", "profit_factor", "max_dd_pips", "annualized_pips"),
    )
    split_df = pd.concat(split_frames, ignore_index=True) if split_frames else pd.DataFrame()
    year_df = pd.concat(year_frames, ignore_index=True) if year_frames else pd.DataFrame()
    sanity_df = build_sanity_summary(sanity_rows)
    trades_df = _concat_trade_frames(trade_frames)

    metadata = {
        "experiment_code": output_code,
        "canonical_experiment_code": "E005",
        "slot_id": params.slot_id,
        "side": params.side,
        "slippage_values": [float(value) for value in slippage_values],
        "entry_delay_seconds": int(params.entry_delay_seconds),
        "ticks_dir": str(ticks_dir),
        "jobs": int(jobs),
        "baseline_comparison_label": params.comparison_label(),
    }
    write_json(paths["metadata_json"], metadata)
    write_json(paths["params_json"], params.to_dict())
    summary_df.to_csv(paths["summary_csv"], index=False)
    split_df.to_csv(paths["split_summary_csv"], index=False)
    year_df.to_csv(paths["year_summary_csv"], index=False)
    trades_df.to_csv(paths["trades_csv"], index=False)
    sanity_df.to_csv(paths["sanity_csv"], index=False)
    print(f"[WRITE][{output_code}] {paths['summary_csv']}")

    return {
        "summary_df": summary_df,
        "split_df": split_df,
        "year_df": year_df,
        "trades_df": trades_df,
        "sanity_df": sanity_df,
    }


def _run_e006(
    *,
    params: E004Params,
    root_out_dir: str | Path,
    baseline: dict[str, object],
    output_code: str = "E006",
) -> dict[str, pd.DataFrame]:
    paths = ensure_run_layout(Path(root_out_dir) / output_code)
    tick_trades_df = baseline["tick_trades_df"]  # type: ignore[index]
    tick_rows_df = baseline["tick_rows_df"]  # type: ignore[index]
    eligible_days_by_segment = baseline["eligible_days_by_segment"]  # type: ignore[index]
    load_summary = baseline["load_summary"]  # type: ignore[index]
    minute_result = baseline["minute_result"]  # type: ignore[index]

    summary_df = _build_walkforward_summary(tick_trades_df)
    split_df = build_split_summary(tick_trades_df, eligible_days_by_segment=eligible_days_by_segment)  # type: ignore[arg-type]
    year_df = build_year_summary(tick_trades_df)
    sanity_df = _aggregate_tick_sanity(
        comparison_label=params.comparison_label(),
        params=params,
        tick_rows=tick_rows_df,
        minute_sanity=minute_result.sanity,
        load_summary=load_summary,
    )
    trades_df = tick_trades_df.copy()

    metadata = {
        "experiment_code": output_code,
        "canonical_experiment_code": "E006",
        "slot_id": params.slot_id,
        "side": params.side,
        "baseline_comparison_label": params.comparison_label(),
        "walkforward_test_years": [2021, 2022, 2023, 2024, 2025],
    }
    write_json(paths["metadata_json"], metadata)
    write_json(paths["params_json"], params.to_dict())
    summary_df.to_csv(paths["summary_csv"], index=False)
    split_df.to_csv(paths["split_summary_csv"], index=False)
    year_df.to_csv(paths["year_summary_csv"], index=False)
    trades_df.to_csv(paths["trades_csv"], index=False)
    sanity_df.to_csv(paths["sanity_csv"], index=False)
    print(f"[WRITE][{output_code}] {paths['summary_csv']}")

    return {
        "summary_df": summary_df,
        "split_df": split_df,
        "year_df": year_df,
        "trades_df": trades_df,
        "sanity_df": sanity_df,
    }


def _run_e007(
    *,
    params: E004Params,
    root_out_dir: str | Path,
    baseline: dict[str, object],
    target_maintenance_margin_candidates: tuple[float, ...],
    initial_capital_jpy: float,
    kill_switch_dd_pct: float,
    output_code: str = "E007",
) -> dict[str, pd.DataFrame]:
    paths = ensure_run_layout(Path(root_out_dir) / output_code)
    tick_trades_df = baseline["tick_trades_df"]  # type: ignore[index]
    tick_rows_df = baseline["tick_rows_df"]  # type: ignore[index]
    eligible_days_by_segment = baseline["eligible_days_by_segment"]  # type: ignore[index]
    load_summary = baseline["load_summary"]  # type: ignore[index]
    minute_result = baseline["minute_result"]  # type: ignore[index]

    summary_frames: list[pd.DataFrame] = []
    equity_frames: list[pd.DataFrame] = []
    for target_margin in tqdm(
        target_maintenance_margin_candidates,
        desc="E007 maintenance margin sweep",
        unit="grid",
        mininterval=0.5,
    ):
        equity_df, summary_df = _build_target_maintenance_margin_outputs(
            trades_df=tick_trades_df,
            initial_capital_jpy=float(initial_capital_jpy),
            target_maintenance_margin_pct=float(target_margin),
            kill_switch_dd_pct=float(kill_switch_dd_pct),
            sl_pips=float(params.baseline.sl_pips),
            eligible_day_count=int(eligible_days_by_segment["full"]),  # type: ignore[index]
        )
        summary_frames.append(summary_df)
        if not equity_df.empty:
            equity_frames.append(equity_df)

    summary_df = _variant_metrics(
        variant_df=pd.concat(summary_frames, ignore_index=True) if summary_frames else pd.DataFrame(),
        baseline_key=target_maintenance_margin_candidates[0] if target_maintenance_margin_candidates else 0.0,
        variant_col="target_maintenance_margin_pct",
        metric_cols=("final_equity_jpy", "min_maintenance_margin_pct", "annualized_pips", "cagr"),
    )
    if not summary_df.empty:
        selected = False
        selected_ranks: list[int | None] = []
        selected_by_rule: list[bool] = []
        for rank, row in enumerate(summary_df.to_dict("records"), start=1):
            row_ok = (
                int(row.get("maintenance_below_100_count", 0)) == 0
                and not bool(row.get("stop_triggered", False))
                and int(row.get("maintenance_below_130_count", 0)) == 0
            )
            if row_ok and not selected:
                selected = True
                selected_ranks.append(rank)
                selected_by_rule.append(True)
            else:
                selected_ranks.append(None)
                selected_by_rule.append(False)
        summary_df["selected_candidate_rank"] = selected_ranks
        summary_df["selected_by_rule"] = selected_by_rule
    split_df = build_split_summary(tick_trades_df, eligible_days_by_segment=eligible_days_by_segment)  # type: ignore[arg-type]
    year_df = build_year_summary(tick_trades_df)
    sanity_df = _aggregate_tick_sanity(
        comparison_label=params.comparison_label(),
        params=params,
        tick_rows=tick_rows_df,
        minute_sanity=minute_result.sanity,
        load_summary=load_summary,
    )
    trades_df = tick_trades_df.copy()
    equity_curve_df = pd.concat(equity_frames, ignore_index=True) if equity_frames else pd.DataFrame()

    metadata = {
        "experiment_code": output_code,
        "canonical_experiment_code": "E007",
        "slot_id": params.slot_id,
        "side": params.side,
        "baseline_comparison_label": params.comparison_label(),
        "target_maintenance_margin_candidates": [float(value) for value in target_maintenance_margin_candidates],
        "initial_capital_jpy": float(initial_capital_jpy),
        "kill_switch_dd_pct": float(kill_switch_dd_pct),
        "maintenance_warning_threshold_pct": 130.0,
        "maintenance_absolute_ng_threshold_pct": 100.0,
        "maintenance_margin_pct_definition": "projected maintenance margin after an immediate SL-sized loss at entry",
        "pips_year_rate_pct_at_150usd_formula": "166.67 / target_maintenance_margin_pct",
    }
    write_json(paths["metadata_json"], metadata)
    write_json(paths["params_json"], params.to_dict())
    summary_df.to_csv(paths["summary_csv"], index=False)
    split_df.to_csv(paths["split_summary_csv"], index=False)
    year_df.to_csv(paths["year_summary_csv"], index=False)
    trades_df.to_csv(paths["trades_csv"], index=False)
    sanity_df.to_csv(paths["sanity_csv"], index=False)
    equity_curve_df.to_csv(paths["root"] / "equity_curve.csv", index=False)
    print(f"[WRITE][{output_code}] {paths['summary_csv']}")

    return {
        "summary_df": summary_df,
        "split_df": split_df,
        "year_df": year_df,
        "trades_df": trades_df,
        "sanity_df": sanity_df,
        "equity_curve_df": equity_curve_df,
    }


def _run_e008(
    *,
    params: E004Params,
    ticks_dir: str | Path,
    jobs: int,
    root_out_dir: str | Path,
    baseline: dict[str, object],
    entry_delay_values: tuple[int, ...],
    output_code: str = "E008",
) -> dict[str, pd.DataFrame]:
    paths = ensure_run_layout(Path(root_out_dir) / output_code)
    signal_rows = [signal.to_dict() for signal in baseline["signals"]]  # type: ignore[index]
    eligible_days_by_segment = baseline["eligible_days_by_segment"]  # type: ignore[index]

    summary_rows: list[dict[str, object]] = []
    year_frames: list[pd.DataFrame] = []
    split_frames: list[pd.DataFrame] = []
    sanity_rows: list[dict[str, object]] = []
    trade_frames: list[pd.DataFrame] = []

    for delay in tqdm(entry_delay_values, desc="E008 delay sweep", unit="grid", mininterval=0.5):
        tick_rows_df = run_tick_replay_batch(
            signal_rows,
            ticks_dir=ticks_dir,
            jobs=jobs,
            slippage_mode=params.slippage_mode,
            fixed_slippage_pips=params.fixed_slippage_pips,
            entry_delay_seconds=int(delay),
        )
        tick_trades_df = _base_tick_trades(tick_rows_df)
        summary_rows.append(
            {
                **_variant_summary_row(
                    trades_df=tick_trades_df,
                    eligible_days_by_segment=eligible_days_by_segment,  # type: ignore[arg-type]
                    variant_col="entry_delay_seconds",
                    variant_value=int(delay),
                ),
                "slip_pips": float(params.fixed_slippage_pips),
            }
        )
        year_frame = build_year_summary(tick_trades_df)
        if not year_frame.empty:
            year_frame["entry_delay_seconds"] = int(delay)
            year_frames.append(year_frame)
        split_frame = build_split_summary(
            tick_trades_df,
            eligible_days_by_segment=eligible_days_by_segment,  # type: ignore[arg-type]
        )
        if not split_frame.empty:
            split_frame["entry_delay_seconds"] = int(delay)
            split_frames.append(split_frame)
        sanity_rows.append(
            _variant_sanity_row(
                tick_rows_df=tick_rows_df,
                variant_col="entry_delay_seconds",
                variant_value=int(delay),
            )
        )
        if not tick_rows_df.empty:
            trade_frame = tick_rows_df.copy()
            trade_frame["entry_delay_seconds"] = int(delay)
            trade_frames.append(trade_frame)

    summary_df = _variant_metrics(
        variant_df=pd.DataFrame(summary_rows),
        baseline_key=0,
        variant_col="entry_delay_seconds",
        metric_cols=("gross_pips", "profit_factor", "max_dd_pips", "annualized_pips"),
    )
    split_df = pd.concat(split_frames, ignore_index=True) if split_frames else pd.DataFrame()
    year_df = pd.concat(year_frames, ignore_index=True) if year_frames else pd.DataFrame()
    sanity_df = build_sanity_summary(sanity_rows)
    trades_df = _concat_trade_frames(trade_frames)

    metadata = {
        "experiment_code": output_code,
        "canonical_experiment_code": "E008",
        "slot_id": params.slot_id,
        "side": params.side,
        "entry_delay_values": [int(value) for value in entry_delay_values],
        "slippage_mode": params.slippage_mode,
        "fixed_slippage_pips": float(params.fixed_slippage_pips),
        "ticks_dir": str(ticks_dir),
        "jobs": int(jobs),
        "baseline_comparison_label": params.comparison_label(),
    }
    write_json(paths["metadata_json"], metadata)
    write_json(paths["params_json"], params.to_dict())
    summary_df.to_csv(paths["summary_csv"], index=False)
    split_df.to_csv(paths["split_summary_csv"], index=False)
    year_df.to_csv(paths["year_summary_csv"], index=False)
    trades_df.to_csv(paths["trades_csv"], index=False)
    sanity_df.to_csv(paths["sanity_csv"], index=False)
    print(f"[WRITE][{output_code}] {paths['summary_csv']}")

    return {
        "summary_df": summary_df,
        "split_df": split_df,
        "year_df": year_df,
        "trades_df": trades_df,
        "sanity_df": sanity_df,
    }


def run_e005_e008(
    *,
    params: E005E008Params,
    dataset_dir: str | Path,
    ticks_dir: str | Path,
    out_dir: str | Path,
    years: list[int],
    jobs: int = 1,
    allow_gate_fail: bool = False,
    only: tuple[str, ...] | None = None,
    output_aliases: dict[str, str] | None = None,
) -> dict[str, dict[str, pd.DataFrame]]:
    if not params.pass_stability_gate and not allow_gate_fail:
        raise ValueError("pass_stability_gate is False; rerun with explicit override if this is intentional")

    selected = tuple(dict.fromkeys(experiment.upper() for experiment in (only or params.selected_experiments)))
    unsupported = [experiment for experiment in selected if experiment not in {"E005", "E006", "E007", "E008"}]
    if unsupported:
        raise ValueError(f"Unsupported experiments in only=: {unsupported}")
    aliases = {key.upper(): value.upper() for key, value in (output_aliases or {}).items()}
    unsupported_aliases = [key for key in aliases if key not in {"E005", "E006", "E007", "E008"}]
    if unsupported_aliases:
        raise ValueError(f"Unsupported output aliases: {unsupported_aliases}")

    baseline_params = params.to_e004_params()

    baseline = _prepare_e004_baseline(
        params=baseline_params,
        dataset_dir=dataset_dir,
        ticks_dir=ticks_dir,
        years=years,
        jobs=jobs,
    )

    resolved_slippage_values = tuple(float(value) for value in params.slippage_values)
    resolved_entry_delay_values = tuple(int(value) for value in params.entry_delay_values)
    resolved_target_margins = tuple(float(value) for value in params.target_maintenance_margin_candidates)
    results: dict[str, dict[str, pd.DataFrame]] = {}

    if "E005" in selected:
        output_code = aliases.get("E005", "E005")
        print(f"[RUN] E005 slippage sweep values={', '.join(f'{value:g}' for value in resolved_slippage_values)}")
        results[output_code] = _run_e005(
            params=baseline_params,
            ticks_dir=ticks_dir,
            jobs=jobs,
            root_out_dir=out_dir,
            baseline=baseline,
            slippage_values=resolved_slippage_values,
            output_code=output_code,
        )

    if "E006" in selected:
        output_code = aliases.get("E006", "E006")
        print("[RUN] E006 walk-forward summary")
        results[output_code] = _run_e006(
            params=baseline_params,
            root_out_dir=out_dir,
            baseline=baseline,
            output_code=output_code,
        )

    if "E007" in selected:
        output_code = aliases.get("E007", "E007")
        print(f"[RUN] E007 maintenance margin sweep values={', '.join(f'{value:g}' for value in resolved_target_margins)}")
        results[output_code] = _run_e007(
            params=baseline_params,
            root_out_dir=out_dir,
            baseline=baseline,
            target_maintenance_margin_candidates=tuple(float(value) for value in resolved_target_margins),
            initial_capital_jpy=float(params.initial_capital_jpy),
            kill_switch_dd_pct=float(params.kill_switch_dd_pct),
            output_code=output_code,
        )

    if "E008" in selected:
        output_code = aliases.get("E008", "E008")
        print(f"[RUN] E008 delay sweep values={', '.join(str(value) for value in resolved_entry_delay_values)}")
        results[output_code] = _run_e008(
            params=baseline_params,
            ticks_dir=ticks_dir,
            jobs=jobs,
            root_out_dir=out_dir,
            baseline=baseline,
            entry_delay_values=resolved_entry_delay_values,
            output_code=output_code,
        )

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    suite_metadata = {
        "experiment_code": "E005-E008",
        "slot_id": params.slot_id,
        "side": params.side,
        "selected": list(selected),
        "output_aliases": aliases,
        "output_experiments": [aliases.get(experiment, experiment) for experiment in selected],
        "dataset_dir": str(dataset_dir),
        "ticks_dir": str(ticks_dir),
        "out_dir": str(out_dir),
        "years": years,
        "jobs": int(jobs),
        "allow_gate_fail": bool(allow_gate_fail),
        "slippage_values": [float(value) for value in resolved_slippage_values],
        "entry_delay_values": [int(value) for value in resolved_entry_delay_values],
        "target_maintenance_margin_candidates": [float(value) for value in resolved_target_margins],
        "initial_capital_jpy": float(params.initial_capital_jpy),
        "kill_switch_dd_pct": float(params.kill_switch_dd_pct),
        "baseline_comparison_label": baseline_params.comparison_label(),
        "pre_range_threshold": baseline["pre_range_threshold"],
        "dynamic_filter_threshold": baseline["dynamic_filter_threshold"],
        "threshold_metadata": baseline["threshold_metadata"],
        "load_summary": asdict(baseline["load_summary"]),  # type: ignore[arg-type,index]
        "signal_day_count": int(len(baseline["signals_df"])),  # type: ignore[arg-type,index]
        "tick_trade_count": int(len(baseline["tick_trades_df"])),  # type: ignore[arg-type,index]
    }
    write_json(Path(out_dir) / "params.json", params.to_dict())
    write_json(Path(out_dir) / "suite_metadata.json", suite_metadata)
    return results
