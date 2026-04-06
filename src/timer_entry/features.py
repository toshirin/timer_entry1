from __future__ import annotations

from dataclasses import dataclass

import math
import pandas as pd


PIP_SIZE = 0.01
DEFAULT_LOOKBACK_START_MIN = 55
DEFAULT_LEFT_END_MIN = 30
DEFAULT_LOOKBACK_END_MIN = 5


@dataclass(frozen=True)
class FeatureWindowSpec:
    # feature 計算窓は scan / qualify / runtime で共通化する。
    # 初版は t-55 .. t-5 を標準とし、左右の分割点は t-30 とする。
    lookback_start_min: int = DEFAULT_LOOKBACK_START_MIN
    left_end_min: int = DEFAULT_LEFT_END_MIN
    lookback_end_min: int = DEFAULT_LOOKBACK_END_MIN


@dataclass(frozen=True)
class FeatureComputationResult:
    # 1 行分の特徴量をそのまま後段へ渡せる形で持つ。
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


def _safe_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _get_row_at_or_before(day_df: pd.DataFrame, target_time: pd.Timestamp) -> pd.Series | None:
    matches = day_df.loc[day_df["Minute_Market"] == target_time]
    if matches.empty:
        return None
    row = matches.iloc[0]
    return row


def build_feature_window(
    day_df: pd.DataFrame,
    *,
    entry_time: pd.Timestamp,
    spec: FeatureWindowSpec = FeatureWindowSpec(),
) -> tuple[pd.DataFrame | None, str]:
    # feature window は entry より前で閉じる。
    # 1分足が欠けていて 51 本そろわない場合は、その日は不採用にする。
    start_time = entry_time - pd.Timedelta(minutes=spec.lookback_start_min)
    end_time = entry_time - pd.Timedelta(minutes=spec.lookback_end_min)
    window = day_df.loc[
        (day_df["Minute_Market"] >= start_time) & (day_df["Minute_Market"] <= end_time)
    ].copy()
    expected_len = spec.lookback_start_min - spec.lookback_end_min + 1
    if window.empty:
        return None, "empty_feature_window"
    if len(window) != expected_len:
        return None, "incomplete_feature_window"
    return window, ""


def compute_feature_row(
    day_df: pd.DataFrame,
    *,
    entry_time: pd.Timestamp,
    spec: FeatureWindowSpec = FeatureWindowSpec(),
) -> FeatureComputationResult:
    # canonical feature 定義:
    # pre_open_slope も左右の形も、すべて Bid の open/close 基準で統一する。
    window, missing_reason = build_feature_window(day_df, entry_time=entry_time, spec=spec)
    if window is None:
        return FeatureComputationResult(
            feature_available=False,
            missing_reason=missing_reason,
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

    start_time = entry_time - pd.Timedelta(minutes=spec.lookback_start_min)
    mid_time = entry_time - pd.Timedelta(minutes=spec.left_end_min)
    end_time = entry_time - pd.Timedelta(minutes=spec.lookback_end_min)

    start_row = _get_row_at_or_before(day_df, start_time)
    mid_row = _get_row_at_or_before(day_df, mid_time)
    end_row = _get_row_at_or_before(day_df, end_time)
    if start_row is None or mid_row is None or end_row is None:
        return FeatureComputationResult(
            feature_available=False,
            missing_reason="missing_required_clock",
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

    required_values = [
        _safe_float(start_row["Bid_Open"]),
        _safe_float(mid_row["Bid_Open"]),
        _safe_float(mid_row["Bid_Close"]),
        _safe_float(end_row["Bid_Close"]),
        _safe_float(window["Bid_High"].max()),
        _safe_float(window["Bid_Low"].min()),
    ]
    if any(value is None for value in required_values):
        return FeatureComputationResult(
            feature_available=False,
            missing_reason="nan_required_value",
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

    start_open = float(start_row["Bid_Open"])
    mid_open = float(mid_row["Bid_Open"])
    mid_close = float(mid_row["Bid_Close"])
    end_close = float(end_row["Bid_Close"])
    pre_range_pips = (float(window["Bid_High"].max()) - float(window["Bid_Low"].min())) / PIP_SIZE

    pre_open_slope_pips = (end_close - start_open) / PIP_SIZE
    left_ret_pips = (mid_close - start_open) / PIP_SIZE
    right_ret_pips = (end_close - mid_open) / PIP_SIZE
    left_abs_pips = abs(left_ret_pips)
    right_abs_pips = abs(right_ret_pips)
    net_move_pips = (end_close - start_open) / PIP_SIZE

    if pre_range_pips <= 0.0:
        trend_ratio = math.nan
    else:
        trend_ratio = abs(net_move_pips) / pre_range_pips

    # runtime と整合させるため、片側 0 は same_sign 側に寄せる。
    same_sign = left_ret_pips == 0.0 or right_ret_pips == 0.0 or (left_ret_pips > 0) == (right_ret_pips > 0)
    opposite_sign = left_ret_pips != 0.0 and right_ret_pips != 0.0 and (left_ret_pips > 0) != (right_ret_pips > 0)

    return FeatureComputationResult(
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


def feature_result_to_dict(result: FeatureComputationResult) -> dict[str, object]:
    return {
        "feature_available": result.feature_available,
        "missing_reason": result.missing_reason,
        "pre_open_slope_pips": result.pre_open_slope_pips,
        "left_ret_pips": result.left_ret_pips,
        "right_ret_pips": result.right_ret_pips,
        "left_abs_pips": result.left_abs_pips,
        "right_abs_pips": result.right_abs_pips,
        "pre_range_pips": result.pre_range_pips,
        "net_move_pips": result.net_move_pips,
        "trend_ratio": result.trend_ratio,
        "same_sign": result.same_sign,
        "opposite_sign": result.opposite_sign,
        "left_stronger": result.left_stronger,
        "right_stronger": result.right_stronger,
    }


__all__ = [
    "DEFAULT_LEFT_END_MIN",
    "DEFAULT_LOOKBACK_END_MIN",
    "DEFAULT_LOOKBACK_START_MIN",
    "FeatureComputationResult",
    "FeatureWindowSpec",
    "PIP_SIZE",
    "build_feature_window",
    "compute_feature_row",
    "feature_result_to_dict",
]
