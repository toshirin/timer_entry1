from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np
import pandas as pd

from .direction import DirectionSpec, get_direction_spec
from .features import PIP_SIZE
from .filters import canonical_filter_labels, evaluate_canonical_filter
from .minute_data import TradingDay


I64_NAT = np.iinfo(np.int64).min
SCAN_LABELS = canonical_filter_labels()

REASON_FORCED_EXIT = 0
REASON_TP = 1
REASON_SL = 2

RESOLVE_FORCED_EXIT = 0
RESOLVE_EVENT_TIME_TP_FIRST = 1
RESOLVE_EVENT_TIME_SL_FIRST = 2
RESOLVE_UNFAVORABLE_SIDE = 3
RESOLVE_SINGLE_HIT_TP = 4
RESOLVE_SINGLE_HIT_SL = 5

REASON_NAME = {
    REASON_FORCED_EXIT: "forced_exit",
    REASON_TP: "tp",
    REASON_SL: "sl",
}

RESOLVE_NAME = {
    RESOLVE_FORCED_EXIT: "forced_exit",
    RESOLVE_EVENT_TIME_TP_FIRST: "event_time_tp_first",
    RESOLVE_EVENT_TIME_SL_FIRST: "event_time_sl_first",
    RESOLVE_UNFAVORABLE_SIDE: "unfavorable_side",
    RESOLVE_SINGLE_HIT_TP: "single_hit_tp",
    RESOLVE_SINGLE_HIT_SL: "single_hit_sl",
}


@dataclass(frozen=True)
class FastFeatureRow:
    feature_available: bool
    missing_reason: str
    pre_open_slope_pips: float
    left_ret_pips: float
    right_ret_pips: float
    left_abs_pips: float
    right_abs_pips: float
    pre_range_pips: float
    net_move_pips: float
    trend_ratio: float
    same_sign: bool
    opposite_sign: bool
    left_stronger: bool
    right_stronger: bool


@dataclass(frozen=True)
class FastDay:
    # scan 用に 1 日分を numpy 配列化した形。
    # day.frame を毎回 iterrows しないため、総当たりでかなり効く。
    session_date: str
    year: int
    session_tz: str
    clock_to_idx: dict[str, int]
    minute_ns: np.ndarray
    bid_open: np.ndarray
    bid_high: np.ndarray
    bid_low: np.ndarray
    bid_close: np.ndarray
    ask_open: np.ndarray
    ask_high: np.ndarray
    ask_low: np.ndarray
    ask_close: np.ndarray
    bid_high_time_ns: np.ndarray
    bid_low_time_ns: np.ndarray
    ask_high_time_ns: np.ndarray
    ask_low_time_ns: np.ndarray


@dataclass(frozen=True)
class FastScanResult:
    daily_df: pd.DataFrame
    summary_df: pd.DataFrame


def _to_i8(values: pd.Series) -> np.ndarray:
    parsed = pd.to_datetime(values, errors="coerce")
    return parsed.astype("int64", copy=False).to_numpy()


def _minute_column(session_tz: str) -> str:
    if session_tz == "Asia/Tokyo":
        return "Minute_JST"
    return "Minute_London"


def preprocess_fast_days(days: Iterable[TradingDay]) -> dict[str, FastDay]:
    out: dict[str, FastDay] = {}
    for day in days:
        frame = day.frame.sort_values(_minute_column(day.session_tz)).reset_index(drop=True)
        clock_to_idx = {str(clock): idx for idx, clock in enumerate(frame["Clock_Market"])}
        out[day.session_date] = FastDay(
            session_date=day.session_date,
            year=day.year,
            session_tz=day.session_tz,
            clock_to_idx=clock_to_idx,
            minute_ns=_to_i8(frame["Minute_Market"]),
            bid_open=frame["Bid_Open"].to_numpy(dtype=np.float64, copy=True),
            bid_high=frame["Bid_High"].to_numpy(dtype=np.float64, copy=True),
            bid_low=frame["Bid_Low"].to_numpy(dtype=np.float64, copy=True),
            bid_close=frame["Bid_Close"].to_numpy(dtype=np.float64, copy=True),
            ask_open=frame["Ask_Open"].to_numpy(dtype=np.float64, copy=True),
            ask_high=frame["Ask_High"].to_numpy(dtype=np.float64, copy=True),
            ask_low=frame["Ask_Low"].to_numpy(dtype=np.float64, copy=True),
            ask_close=frame["Ask_Close"].to_numpy(dtype=np.float64, copy=True),
            bid_high_time_ns=_to_i8(frame["Bid_High_Time"]),
            bid_low_time_ns=_to_i8(frame["Bid_Low_Time"]),
            ask_high_time_ns=_to_i8(frame["Ask_High_Time"]),
            ask_low_time_ns=_to_i8(frame["Ask_Low_Time"]),
        )
    return out


def _empty_feature_row(reason: str) -> FastFeatureRow:
    return FastFeatureRow(
        feature_available=False,
        missing_reason=reason,
        pre_open_slope_pips=math.nan,
        left_ret_pips=math.nan,
        right_ret_pips=math.nan,
        left_abs_pips=math.nan,
        right_abs_pips=math.nan,
        pre_range_pips=math.nan,
        net_move_pips=math.nan,
        trend_ratio=math.nan,
        same_sign=False,
        opposite_sign=False,
        left_stronger=False,
        right_stronger=False,
    )


def compute_fast_feature_row(day: FastDay, *, entry_idx: int) -> FastFeatureRow:
    # canonical feature を位置ベースで高速計算する。
    # 55 / 30 / 5 分前が厳密に存在しない日は落とす。
    start_idx = entry_idx - 55
    mid_idx = entry_idx - 30
    end_idx = entry_idx - 5
    if start_idx < 0 or mid_idx < 0 or end_idx < 0:
        return _empty_feature_row("insufficient_history")

    expected_step_ns = 60 * 1_000_000_000
    if (
        day.minute_ns[entry_idx] - day.minute_ns[start_idx] != 55 * expected_step_ns
        or day.minute_ns[entry_idx] - day.minute_ns[mid_idx] != 30 * expected_step_ns
        or day.minute_ns[entry_idx] - day.minute_ns[end_idx] != 5 * expected_step_ns
    ):
        return _empty_feature_row("incomplete_feature_window")

    window_bid_high = day.bid_high[start_idx : end_idx + 1]
    window_bid_low = day.bid_low[start_idx : end_idx + 1]
    if (
        not np.isfinite(day.bid_open[start_idx])
        or not np.isfinite(day.bid_open[mid_idx])
        or not np.isfinite(day.bid_close[mid_idx])
        or not np.isfinite(day.bid_close[end_idx])
        or not np.isfinite(window_bid_high).all()
        or not np.isfinite(window_bid_low).all()
    ):
        return _empty_feature_row("nan_required_value")

    start_open = float(day.bid_open[start_idx])
    mid_open = float(day.bid_open[mid_idx])
    mid_close = float(day.bid_close[mid_idx])
    end_close = float(day.bid_close[end_idx])
    pre_range_pips = float(window_bid_high.max() - window_bid_low.min()) / PIP_SIZE
    pre_open_slope_pips = (end_close - start_open) / PIP_SIZE
    left_ret_pips = (mid_close - start_open) / PIP_SIZE
    right_ret_pips = (end_close - mid_open) / PIP_SIZE
    left_abs_pips = abs(left_ret_pips)
    right_abs_pips = abs(right_ret_pips)
    net_move_pips = (end_close - start_open) / PIP_SIZE
    trend_ratio = math.nan if pre_range_pips <= 0.0 else abs(net_move_pips) / pre_range_pips
    same_sign = left_ret_pips == 0.0 or right_ret_pips == 0.0 or (left_ret_pips > 0.0) == (right_ret_pips > 0.0)
    opposite_sign = left_ret_pips != 0.0 and right_ret_pips != 0.0 and (left_ret_pips > 0.0) != (right_ret_pips > 0.0)

    return FastFeatureRow(
        feature_available=True,
        missing_reason="",
        pre_open_slope_pips=float(pre_open_slope_pips),
        left_ret_pips=float(left_ret_pips),
        right_ret_pips=float(right_ret_pips),
        left_abs_pips=float(left_abs_pips),
        right_abs_pips=float(right_abs_pips),
        pre_range_pips=float(pre_range_pips),
        net_move_pips=float(net_move_pips),
        trend_ratio=float(trend_ratio) if not math.isnan(trend_ratio) else math.nan,
        same_sign=bool(same_sign),
        opposite_sign=bool(opposite_sign),
        left_stronger=bool(left_abs_pips > right_abs_pips),
        right_stronger=bool(right_abs_pips > left_abs_pips),
    )


def _feature_labels(features: FastFeatureRow, *, pre_range_median: float | None) -> list[str]:
    labels: list[str] = []
    for label in SCAN_LABELS:
        if label in {"vol_ge_med", "vol_lt_med"} and pre_range_median is None:
            continue
        if evaluate_canonical_filter(label, features, pre_range_median=pre_range_median):
            labels.append(label)
    return labels


def _entry_array(day: FastDay, spec: DirectionSpec) -> np.ndarray:
    return day.ask_open if spec.entry_col == "Ask_Open" else day.bid_open


def _tp_hit_array(day: FastDay, spec: DirectionSpec) -> np.ndarray:
    if spec.tp_hit_col == "Bid_High":
        return day.bid_high
    return day.ask_low


def _sl_hit_array(day: FastDay, spec: DirectionSpec) -> np.ndarray:
    if spec.sl_hit_col == "Ask_Low":
        return day.ask_low
    return day.bid_high


def _forced_exit_array(day: FastDay, spec: DirectionSpec) -> np.ndarray:
    if spec.forced_exit_col == "Bid_Close":
        return day.bid_close
    return day.ask_close


def _tp_time_array(day: FastDay, spec: DirectionSpec) -> np.ndarray:
    if spec.tp_time_col == "Bid_High_Time":
        return day.bid_high_time_ns
    return day.ask_low_time_ns


def _sl_time_array(day: FastDay, spec: DirectionSpec) -> np.ndarray:
    if spec.sl_time_col == "Ask_Low_Time":
        return day.ask_low_time_ns
    return day.bid_high_time_ns


def simulate_fast_matrix(
    *,
    day: FastDay,
    spec: DirectionSpec,
    entry_idx: int,
    exit_idx: int,
    sl_grid_pips: np.ndarray,
    tp_grid_pips: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    # scan 用の本体。
    # 全 SL / TP グリッドを同時に処理しつつ、canonical の保守的 SL exit を守る。
    entry_array = _entry_array(day, spec)
    entry_price = float(entry_array[entry_idx])
    entry_spread = float(day.ask_open[entry_idx] - day.bid_open[entry_idx])

    sl_trigger_levels = entry_price + spec.sl_sign * (sl_grid_pips.astype(np.float64) * PIP_SIZE)
    if spec.side == "buy":
        sl_exit_levels = sl_trigger_levels - entry_spread
    else:
        sl_exit_levels = sl_trigger_levels + entry_spread
    tp_exit_levels = entry_price + spec.tp_sign * (tp_grid_pips.astype(np.float64) * PIP_SIZE)

    shape = (len(sl_grid_pips), len(tp_grid_pips))
    resolved = np.zeros(shape, dtype=bool)
    exits = np.full(shape, np.nan, dtype=np.float64)
    holds = np.full(shape, exit_idx - entry_idx, dtype=np.int16)
    reason = np.full(shape, REASON_FORCED_EXIT, dtype=np.int8)
    resolve = np.full(shape, RESOLVE_FORCED_EXIT, dtype=np.int8)
    same_bar_unresolved = np.zeros(shape, dtype=bool)

    sl_exit_grid = np.broadcast_to(sl_exit_levels[:, None], shape)
    tp_exit_grid = np.broadcast_to(tp_exit_levels[None, :], shape)

    sl_hits_series = _sl_hit_array(day, spec)
    tp_hits_series = _tp_hit_array(day, spec)
    sl_times = _sl_time_array(day, spec)
    tp_times = _tp_time_array(day, spec)

    for idx in range(entry_idx + 1, exit_idx + 1):
        if spec.side == "buy":
            sl_hit = np.isfinite(sl_hits_series[idx]) & (float(sl_hits_series[idx]) <= sl_trigger_levels)
            tp_hit = np.isfinite(tp_hits_series[idx]) & (float(tp_hits_series[idx]) >= tp_exit_levels)
        else:
            sl_hit = np.isfinite(sl_hits_series[idx]) & (float(sl_hits_series[idx]) >= sl_trigger_levels)
            tp_hit = np.isfinite(tp_hits_series[idx]) & (float(tp_hits_series[idx]) <= tp_exit_levels)

        if (not np.any(sl_hit)) and (not np.any(tp_hit)):
            continue

        unresolved = ~resolved

        sl_only = unresolved & sl_hit[:, None] & (~tp_hit[None, :])
        if sl_only.any():
            exits[sl_only] = sl_exit_grid[sl_only]
            holds[sl_only] = idx - entry_idx
            reason[sl_only] = REASON_SL
            resolve[sl_only] = RESOLVE_SINGLE_HIT_SL
            resolved[sl_only] = True

        tp_only = unresolved & (~sl_hit[:, None]) & tp_hit[None, :]
        if tp_only.any():
            exits[tp_only] = tp_exit_grid[tp_only]
            holds[tp_only] = idx - entry_idx
            reason[tp_only] = REASON_TP
            resolve[tp_only] = RESOLVE_SINGLE_HIT_TP
            resolved[tp_only] = True

        both = unresolved & sl_hit[:, None] & tp_hit[None, :]
        if both.any():
            sl_t = int(sl_times[idx])
            tp_t = int(tp_times[idx])
            unresolved_time = sl_t == I64_NAT or tp_t == I64_NAT or sl_t == tp_t
            if unresolved_time:
                exits[both] = sl_exit_grid[both]
                holds[both] = idx - entry_idx
                reason[both] = REASON_SL
                resolve[both] = RESOLVE_UNFAVORABLE_SIDE
                same_bar_unresolved[both] = True
            elif tp_t < sl_t:
                exits[both] = tp_exit_grid[both]
                holds[both] = idx - entry_idx
                reason[both] = REASON_TP
                resolve[both] = RESOLVE_EVENT_TIME_TP_FIRST
            else:
                exits[both] = sl_exit_grid[both]
                holds[both] = idx - entry_idx
                reason[both] = REASON_SL
                resolve[both] = RESOLVE_EVENT_TIME_SL_FIRST
            resolved[both] = True

        if resolved.all():
            break

    forced_exit_price = float(_forced_exit_array(day, spec)[exit_idx])
    exits[~resolved] = forced_exit_price
    pnl = ((exits - entry_price) / PIP_SIZE).astype(np.float64)
    if spec.side == "sell":
        pnl *= -1.0
    return pnl, holds, reason, resolve, same_bar_unresolved


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


def build_fast_summary(daily_df: pd.DataFrame) -> pd.DataFrame:
    if daily_df.empty:
        return pd.DataFrame(
            columns=[
                "slot_id",
                "side",
                "filter_label",
                "entry_clock_local",
                "sl_pips",
                "tp_pips",
                "trade_count",
                "gross_pips",
                "win_rate",
                "profit_factor",
                "max_dd_pips",
                "max_hold_time_min",
                "same_bar_conflict_count",
                "same_bar_unresolved_count",
                "forced_exit_count",
            ]
        )

    rows: list[dict[str, object]] = []
    group_cols = ["slot_id", "side", "filter_label", "entry_clock_local", "sl_pips", "tp_pips"]
    for key, group in daily_df.groupby(group_cols, sort=False):
        pnl = group["pnl_pips"]
        rows.append(
            {
                "slot_id": key[0],
                "side": key[1],
                "filter_label": key[2],
                "entry_clock_local": key[3],
                "sl_pips": key[4],
                "tp_pips": key[5],
                "trade_count": int(len(group)),
                "gross_pips": float(pnl.sum()),
                "win_rate": float((pnl > 0.0).mean()) if len(group) else math.nan,
                "profit_factor": float(_safe_profit_factor(pnl)),
                "max_dd_pips": float(_safe_max_dd(pnl)),
                "max_hold_time_min": int(group["hold_min"].max()) if len(group) else math.nan,
                "same_bar_conflict_count": int(group["same_bar_conflict_flag"].sum()),
                "same_bar_unresolved_count": int(group["same_bar_unresolved_flag"].sum()),
                "forced_exit_count": int((group["exit_reason"] == "forced_exit").sum()),
            }
        )
    return pd.DataFrame(rows)


def run_scan_fast(
    prepared_days: dict[str, FastDay],
    *,
    slot_id: str,
    side: str,
    entry_clock_local: str,
    exit_after_minutes: int,
    sl_grid_pips: Iterable[float],
    tp_grid_pips: Iterable[float],
    pre_range_median: float | None = None,
) -> FastScanResult:
    # scan 用の高速総当たり runner。
    # filter family 探しを主目的にし、1 日 x 1 entry slot の全 SL/TP をまとめて処理する。
    spec = get_direction_spec(side)
    sl_grid = np.asarray(list(sl_grid_pips), dtype=np.float32)
    tp_grid = np.asarray(list(tp_grid_pips), dtype=np.float32)

    rows: list[dict[str, object]] = []
    for day in prepared_days.values():
        entry_idx = day.clock_to_idx.get(entry_clock_local)
        if entry_idx is None:
            continue
        exit_idx = entry_idx + int(exit_after_minutes)
        if exit_idx >= len(day.minute_ns) or exit_idx <= entry_idx:
            continue

        features = compute_fast_feature_row(day, entry_idx=entry_idx)
        if not features.feature_available:
            continue

        filter_labels = _feature_labels(features, pre_range_median=pre_range_median)
        if not filter_labels:
            continue

        pnl_mat, hold_mat, reason_mat, resolve_mat, unresolved_mat = simulate_fast_matrix(
            day=day,
            spec=spec,
            entry_idx=entry_idx,
            exit_idx=exit_idx,
            sl_grid_pips=sl_grid,
            tp_grid_pips=tp_grid,
        )

        same_bar_conflict_mat = np.isin(
            resolve_mat,
            [RESOLVE_EVENT_TIME_TP_FIRST, RESOLVE_EVENT_TIME_SL_FIRST, RESOLVE_UNFAVORABLE_SIDE],
        )

        for filter_label in filter_labels:
            for sl_i, sl_pips in enumerate(sl_grid.tolist()):
                for tp_i, tp_pips in enumerate(tp_grid.tolist()):
                    rows.append(
                        {
                            "slot_id": slot_id,
                            "side": spec.side,
                            "date_local": day.session_date,
                            "year": int(day.year),
                            "entry_clock_local": entry_clock_local,
                            "filter_label": filter_label,
                            "sl_pips": float(sl_pips),
                            "tp_pips": float(tp_pips),
                            "pnl_pips": float(pnl_mat[sl_i, tp_i]),
                            "hold_min": int(hold_mat[sl_i, tp_i]),
                            "exit_reason": REASON_NAME[int(reason_mat[sl_i, tp_i])],
                            "conflict_resolved_by": RESOLVE_NAME[int(resolve_mat[sl_i, tp_i])],
                            "same_bar_conflict_flag": bool(same_bar_conflict_mat[sl_i, tp_i]),
                            "same_bar_unresolved_flag": bool(unresolved_mat[sl_i, tp_i]),
                            "pre_open_slope_pips": float(features.pre_open_slope_pips),
                            "left_ret_pips": float(features.left_ret_pips),
                            "right_ret_pips": float(features.right_ret_pips),
                            "pre_range_pips": float(features.pre_range_pips),
                            "trend_ratio": float(features.trend_ratio) if not math.isnan(features.trend_ratio) else math.nan,
                            "price_series_used": str(spec.price_series_used),
                        }
                    )

    daily_df = pd.DataFrame(rows)
    summary_df = build_fast_summary(daily_df)
    return FastScanResult(daily_df=daily_df, summary_df=summary_df)


__all__ = [
    "FastDay",
    "FastFeatureRow",
    "FastScanResult",
    "build_fast_summary",
    "compute_fast_feature_row",
    "preprocess_fast_days",
    "run_scan_fast",
    "simulate_fast_matrix",
]
