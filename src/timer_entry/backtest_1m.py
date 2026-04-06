from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import pandas as pd

from .direction import DirectionSpec, get_direction_spec
from .features import PIP_SIZE, compute_feature_row
from .filters import evaluate_canonical_filter
from .minute_data import TradingDay
from .schemas import BacktestSummary, BacktestTrade, SanitySummary, StrategySetting


@dataclass(frozen=True)
class BacktestRunResult:
    # qualify 側で扱いやすいように、
    # trade / summary / sanity をまとめて返す。
    trades: list[BacktestTrade]
    summary: BacktestSummary
    sanity: SanitySummary


@dataclass
class _SanityCounter:
    entry_equals_exit_count: int = 0
    entry_equals_exit_sl_count: int = 0
    same_bar_conflict_count: int = 0
    same_bar_unresolved_count: int = 0
    forced_exit_count: int = 0
    forced_exit_missing_count: int = 0
    feature_skip_count: int = 0
    filter_skip_count: int = 0
    tp_time_missing_count: int = 0
    sl_time_missing_count: int = 0


def _safe_profit_factor(values: list[float]) -> float:
    gains = sum(value for value in values if value > 0.0)
    losses = -sum(value for value in values if value < 0.0)
    if losses == 0.0:
        return math.inf if gains > 0.0 else math.nan
    return gains / losses


def _safe_max_dd(values: list[float]) -> float:
    if not values:
        return math.nan
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd


def _build_summary(
    trades: list[BacktestTrade],
    *,
    filter_label: str | None,
    eligible_day_count: int,
) -> BacktestSummary:
    pnl_values = [trade.pnl_pips for trade in trades]
    trade_count = len(pnl_values)
    if not pnl_values:
        return BacktestSummary(
            trade_count=0,
            gross_pips=0.0,
            mean_pips=math.nan,
            median_pips=math.nan,
            std_pips=math.nan,
            win_rate=math.nan,
            profit_factor=math.nan,
            max_dd_pips=math.nan,
            annualized_pips=math.nan,
            eligible_day_count=eligible_day_count,
            filter_label=filter_label,
        )

    pnl_series = pd.Series(pnl_values, dtype=float)
    years = sorted({trade.date_local[:4] for trade in trades})
    year_count = len(years)
    gross_pips = float(pnl_series.sum())
    annualized_pips = gross_pips / year_count if year_count > 0 else math.nan

    return BacktestSummary(
        trade_count=trade_count,
        gross_pips=gross_pips,
        mean_pips=float(pnl_series.mean()),
        median_pips=float(pnl_series.median()),
        std_pips=float(pnl_series.std(ddof=0)),
        win_rate=float((pnl_series > 0.0).mean()),
        profit_factor=float(_safe_profit_factor(pnl_values)),
        max_dd_pips=float(_safe_max_dd(pnl_values)),
        annualized_pips=float(annualized_pips),
        eligible_day_count=eligible_day_count,
        filter_label=filter_label,
    )


def _build_sanity_summary(
    spec: DirectionSpec,
    counters: _SanityCounter,
    *,
    time_jst_fallback_count: int,
    duplicate_clock_removed_count: int,
) -> SanitySummary:
    notes = (
        f"filter_skip_count={counters.filter_skip_count}, "
        f"tp_time_missing_count={counters.tp_time_missing_count}, "
        f"sl_time_missing_count={counters.sl_time_missing_count}"
    )
    return SanitySummary(
        entry_price_series=spec.entry_series_name,
        tp_price_series=spec.tp_series_name,
        sl_price_series=spec.sl_series_name,
        forced_exit_price_series=spec.forced_exit_series_name,
        entry_equals_exit_count=counters.entry_equals_exit_count,
        entry_equals_exit_sl_count=counters.entry_equals_exit_sl_count,
        same_bar_conflict_count=counters.same_bar_conflict_count,
        same_bar_unresolved_count=counters.same_bar_unresolved_count,
        forced_exit_count=counters.forced_exit_count,
        forced_exit_missing_count=counters.forced_exit_missing_count,
        feature_skip_count=counters.feature_skip_count,
        time_jst_fallback_count=time_jst_fallback_count,
        duplicate_clock_removed_count=duplicate_clock_removed_count,
        notes=notes,
    )


def _parse_event_time(value: object, market_tz: str) -> pd.Timestamp | None:
    if value is None or pd.isna(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.tz_localize(market_tz, nonexistent="NaT", ambiguous="NaT")
    else:
        parsed = parsed.tz_convert(market_tz)
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed)


def _clock_columns(market_tz: str) -> tuple[str, str]:
    if market_tz == "Asia/Tokyo":
        return "Clock_JST", "Minute_JST"
    return "Clock_London", "Minute_London"


def _row_at(day: TradingDay, clock_hhmm: str) -> pd.Series | None:
    clock_col, _ = _clock_columns(day.session_tz)
    if clock_hhmm not in day.frame.index:
        matches = day.frame.loc[day.frame[clock_col] == clock_hhmm]
        if matches.empty:
            return None
        row = matches.iloc[0]
        return row
    row = day.frame.loc[clock_hhmm]
    if isinstance(row, pd.DataFrame):
        return row.iloc[0]
    return row


def _build_trade_id(setting: StrategySetting, day: TradingDay) -> str:
    date_text = day.session_date.replace("-", "")
    entry_text = setting.normalized_entry_clock().replace(":", "")
    return f"{setting.setting_id}#{date_text}#{entry_text}"


def _entry_spread(entry_row: pd.Series) -> float:
    return float(entry_row["Ask_Open"]) - float(entry_row["Bid_Open"])


def _tp_exit_price(entry_price: float, tp_pips: float, spec: DirectionSpec) -> float:
    return entry_price + spec.tp_sign * tp_pips * PIP_SIZE


def _sl_trigger_price(entry_price: float, sl_pips: float, spec: DirectionSpec) -> float:
    return entry_price + spec.sl_sign * sl_pips * PIP_SIZE


def _conservative_sl_exit_price(sl_trigger_price: float, entry_spread: float, spec: DirectionSpec) -> float:
    # spread を落とさない保守モデルを canonical にする。
    # Buy は Ask trigger から spread 分だけ不利な Bid exit、
    # Sell は Bid trigger から spread 分だけ不利な Ask exit とみなす。
    if spec.side == "buy":
        return sl_trigger_price - entry_spread
    return sl_trigger_price + entry_spread


def _pnl_pips(entry_price: float, exit_price: float, side: str) -> float:
    diff = exit_price - entry_price
    return diff / PIP_SIZE if side == "buy" else -diff / PIP_SIZE


def _filter_label_for_summary(setting: StrategySetting) -> str | None:
    if not setting.filter_labels:
        return None
    return ",".join(setting.filter_labels)


def _simulate_trade_for_day(
    day: TradingDay,
    setting: StrategySetting,
    spec: DirectionSpec,
    counters: _SanityCounter,
) -> BacktestTrade | None:
    entry_clock = setting.normalized_entry_clock()
    forced_exit_clock = setting.normalized_forced_exit_clock()
    _, minute_col = _clock_columns(day.session_tz)

    entry_row = _row_at(day, entry_clock)
    forced_row = _row_at(day, forced_exit_clock)
    if entry_row is None or forced_row is None:
        counters.forced_exit_missing_count += 1
        return None

    if any(pd.isna(entry_row[col]) for col in ("Ask_Open", "Bid_Open")):
        return None
    if pd.isna(forced_row[spec.forced_exit_col]):
        counters.forced_exit_missing_count += 1
        return None

    entry_time = pd.Timestamp(entry_row[minute_col])
    forced_exit_time = pd.Timestamp(forced_row[minute_col])
    if forced_exit_time <= entry_time:
        counters.forced_exit_missing_count += 1
        return None

    feature_result = compute_feature_row(day.frame, entry_time=entry_time)
    if not feature_result.feature_available:
        counters.feature_skip_count += 1
        return None

    for label in setting.filter_labels:
        if not evaluate_canonical_filter(label, feature_result, pre_range_median=setting.pre_range_threshold):
            counters.filter_skip_count += 1
            return None

    entry_price = float(entry_row[spec.entry_col])
    entry_spread = _entry_spread(entry_row)
    tp_exit_price = _tp_exit_price(entry_price, setting.tp_pips, spec)
    sl_trigger_price = _sl_trigger_price(entry_price, setting.sl_pips, spec)
    sl_exit_price = _conservative_sl_exit_price(sl_trigger_price, entry_spread, spec)

    monitor_df = day.frame.loc[
        (day.frame[minute_col] > entry_time) & (day.frame[minute_col] <= forced_exit_time)
    ].copy()

    exit_reason = "forced_exit"
    exit_time = forced_exit_time
    exit_price = float(forced_row[spec.forced_exit_col])
    conflict_resolved_by = "forced_exit"

    for _, row in monitor_df.iterrows():
        tp_hit = not pd.isna(row[spec.tp_hit_col]) and (
            float(row[spec.tp_hit_col]) >= tp_exit_price if spec.side == "buy" else float(row[spec.tp_hit_col]) <= tp_exit_price
        )
        sl_hit = not pd.isna(row[spec.sl_hit_col]) and (
            float(row[spec.sl_hit_col]) <= sl_trigger_price if spec.side == "buy" else float(row[spec.sl_hit_col]) >= sl_trigger_price
        )
        if not tp_hit and not sl_hit:
            continue

        exit_time = pd.Timestamp(row[minute_col])
        if tp_hit and sl_hit:
            counters.same_bar_conflict_count += 1
            tp_time = _parse_event_time(row.get(spec.tp_time_col) if spec.tp_time_col else None, day.session_tz)
            sl_time = _parse_event_time(row.get(spec.sl_time_col) if spec.sl_time_col else None, day.session_tz)
            if tp_time is None:
                counters.tp_time_missing_count += 1
            if sl_time is None:
                counters.sl_time_missing_count += 1

            if tp_time is not None and sl_time is not None and tp_time != sl_time:
                if tp_time < sl_time:
                    exit_reason = "tp"
                    exit_price = tp_exit_price
                    conflict_resolved_by = "event_time_tp_first"
                else:
                    exit_reason = "sl"
                    exit_price = sl_exit_price
                    conflict_resolved_by = "event_time_sl_first"
            else:
                counters.same_bar_unresolved_count += 1
                exit_reason = "sl"
                exit_price = sl_exit_price
                conflict_resolved_by = "unfavorable_side"
            break

        if tp_hit:
            exit_reason = "tp"
            exit_price = tp_exit_price
            conflict_resolved_by = "single_hit_tp"
            break

        exit_reason = "sl"
        exit_price = sl_exit_price
        conflict_resolved_by = "single_hit_sl"
        break

    if exit_reason == "forced_exit":
        counters.forced_exit_count += 1

    if exit_time == entry_time:
        counters.entry_equals_exit_count += 1
        if exit_reason == "sl":
            counters.entry_equals_exit_sl_count += 1

    hold_minutes = int((exit_time - entry_time).total_seconds() / 60.0)
    notes = f"conflict_resolved_by={conflict_resolved_by}"
    return BacktestTrade(
        trade_id=_build_trade_id(setting, day),
        date_local=day.session_date,
        side=spec.side,
        entry_time=entry_time.isoformat(sep=" "),
        entry_price=float(entry_price),
        exit_time=exit_time.isoformat(sep=" "),
        exit_price=float(exit_price),
        exit_reason=exit_reason,
        pnl_pips=float(_pnl_pips(entry_price, exit_price, spec.side)),
        hold_minutes=hold_minutes,
        entry_price_series=spec.entry_series_name,
        exit_price_series=spec.exit_price_side,
        tp_price_series=spec.tp_series_name,
        sl_price_series=spec.sl_series_name,
        forced_exit_price_series=spec.forced_exit_series_name,
        filter_label=_filter_label_for_summary(setting),
        notes=notes,
    )


def run_backtest_1m(
    days: Iterable[TradingDay],
    setting: StrategySetting,
    *,
    time_jst_fallback_count: int = 0,
    duplicate_clock_removed_count: int = 0,
) -> BacktestRunResult:
    # canonical pandas engine。
    # 実装の読みやすさと監査容易性を優先し、
    # scan 高速 engine の仕様親玉として扱う。
    spec = get_direction_spec(setting.side)
    counters = _SanityCounter()
    trades: list[BacktestTrade] = []
    eligible_day_count = 0

    for day in days:
        if day.session_tz != setting.market_tz:
            continue

        entry_row = _row_at(day, setting.normalized_entry_clock())
        forced_row = _row_at(day, setting.normalized_forced_exit_clock())
        if entry_row is None or forced_row is None:
            counters.forced_exit_missing_count += 1
            continue

        _, minute_col = _clock_columns(day.session_tz)
        entry_time = pd.Timestamp(entry_row[minute_col])
        feature_result = compute_feature_row(day.frame, entry_time=entry_time)
        if not feature_result.feature_available:
            counters.feature_skip_count += 1
            continue

        eligible_day_count += 1
        trade = _simulate_trade_for_day(day, setting, spec, counters)
        if trade is not None:
            trades.append(trade)

    summary = _build_summary(
        trades,
        filter_label=_filter_label_for_summary(setting),
        eligible_day_count=eligible_day_count,
    )
    sanity = _build_sanity_summary(
        spec,
        counters,
        time_jst_fallback_count=time_jst_fallback_count,
        duplicate_clock_removed_count=duplicate_clock_removed_count,
    )
    return BacktestRunResult(trades=trades, summary=summary, sanity=sanity)


__all__ = [
    "BacktestRunResult",
    "run_backtest_1m",
]
