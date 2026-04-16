from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from timer_entry.features import FeatureComputationResult
from timer_entry.filters import (
    evaluate_canonical_filter,
    get_filter_family,
    parse_opposite_right_dominance_filter_label,
    parse_right_dominance_filter_label,
    parse_slope_filter_label,
    parse_trend_ratio_filter_label,
    parse_volatility_filter_label,
    to_runtime_filter_spec,
)


def _feature_row(
    *,
    slope: float,
    pre_range: float,
    trend_ratio: float = 0.5,
    right_strength_balance: float = 1.0,
    opposite_sign: bool = False,
) -> FeatureComputationResult:
    return FeatureComputationResult(
        feature_available=True,
        missing_reason="",
        pre_open_slope_pips=slope,
        left_ret_pips=1.0,
        right_ret_pips=1.0,
        left_abs_pips=1.0,
        right_abs_pips=1.0,
        right_strength_balance_pips=right_strength_balance,
        pre_range_pips=pre_range,
        net_move_pips=slope,
        trend_ratio=trend_ratio,
        same_sign=True,
        opposite_sign=opposite_sign,
        left_stronger=False,
        right_stronger=False,
    )


def test_parse_slope_filter_label_supports_extended_thresholds() -> None:
    assert parse_slope_filter_label("ge2") == ("ge", 2.0)
    assert parse_slope_filter_label("le1_5") == ("le", 1.5)


def test_parse_volatility_filter_label_supports_percentiles() -> None:
    assert parse_volatility_filter_label("vol_ge_med") == ("ge", "med")
    assert parse_volatility_filter_label("vol_ge_p60") == ("ge", 60)
    assert parse_volatility_filter_label("vol_lt_p40") == ("lt", 40)
    assert parse_volatility_filter_label("vol_lt_p30") == ("lt", 30)


def test_parse_right_dominance_filter_label_supports_thresholds() -> None:
    assert parse_right_dominance_filter_label("right_dom_ge4") == ("ge", 4.0)


def test_parse_opposite_right_dominance_filter_label_supports_thresholds() -> None:
    assert parse_opposite_right_dominance_filter_label("opp_right_dom_ge2") == ("ge", 2.0)
    assert parse_opposite_right_dominance_filter_label("opp_right_dom_ge4") == ("ge", 4.0)
    assert parse_opposite_right_dominance_filter_label("opp_right_dom_ge6") == ("ge", 6.0)


def test_parse_trend_ratio_filter_label_supports_range_thresholds() -> None:
    assert parse_trend_ratio_filter_label("trend_ge_0_5") == ("ge", 0.5)
    assert parse_trend_ratio_filter_label("range_lt_0_3") == ("lt", 0.3)
    assert parse_trend_ratio_filter_label("range_lt_0_20") == ("lt", 0.2)
    assert parse_trend_ratio_filter_label("range_lt_0_25") == ("lt", 0.25)
    assert parse_trend_ratio_filter_label("range_lt_0_30") == ("lt", 0.3)
    assert parse_trend_ratio_filter_label("range_lt_0_35") == ("lt", 0.35)


def test_evaluate_canonical_filter_supports_extended_slope_labels() -> None:
    features = _feature_row(slope=3.0, pre_range=12.0)
    assert evaluate_canonical_filter("ge2", features) is True
    assert evaluate_canonical_filter("ge4", features) is False
    assert evaluate_canonical_filter("le4", features) is True


def test_evaluate_canonical_filter_supports_volatility_percentiles_with_explicit_threshold() -> None:
    features = _feature_row(slope=0.0, pre_range=12.0)
    assert evaluate_canonical_filter("vol_ge_p60", features, pre_range_threshold=10.0) is True
    assert evaluate_canonical_filter("vol_lt_p40", features, pre_range_threshold=10.0) is False
    with pytest.raises(ValueError):
        evaluate_canonical_filter("vol_ge_p60", features)


def test_to_runtime_filter_spec_supports_extended_labels() -> None:
    slope_spec = to_runtime_filter_spec("ge2")
    assert slope_spec is not None
    assert slope_spec.threshold == 2.0

    vol_spec = to_runtime_filter_spec("vol_ge_p70", pre_range_threshold=15.0)
    assert vol_spec is not None
    assert vol_spec.threshold == 15.0

    right_dom_spec = to_runtime_filter_spec("right_dom_ge4", dynamic_threshold=4.0)
    assert right_dom_spec is not None
    assert right_dom_spec.mode == "right_strength_balance"
    assert right_dom_spec.threshold == 4.0

    opp_right_dom_spec = to_runtime_filter_spec("opp_right_dom_ge6")
    assert opp_right_dom_spec is not None
    assert opp_right_dom_spec.mode == "opposite_sign_right_strength_balance"
    assert opp_right_dom_spec.operator == "ge"
    assert opp_right_dom_spec.threshold == 6.0

    trend_spec = to_runtime_filter_spec("range_lt_0_25")
    assert trend_spec is not None
    assert trend_spec.filter_type == "trend_ratio"
    assert trend_spec.operator == "lt"
    assert trend_spec.threshold == 0.25


def test_get_filter_family_supports_extended_labels() -> None:
    assert get_filter_family("ge4") == "pre_open_slope"
    assert get_filter_family("vol_ge_p70") == "pre_range_regime"
    assert get_filter_family("right_dom_ge4") == "shape_balance"
    assert get_filter_family("opp_right_dom_ge4") == "shape_balance"
    assert get_filter_family("range_lt_0_25") == "trend_ratio"


def test_evaluate_canonical_filter_supports_right_dominance_thresholds() -> None:
    features = _feature_row(slope=0.0, pre_range=12.0)
    assert evaluate_canonical_filter("right_dom_ge4", features, dynamic_threshold=0.5) is True
    assert evaluate_canonical_filter("right_dom_ge4", features, dynamic_threshold=1.5) is False
    assert evaluate_canonical_filter("right_dom_ge4", features) is False


def test_evaluate_canonical_filter_supports_opposite_right_dominance_thresholds() -> None:
    not_opposite = _feature_row(slope=0.0, pre_range=12.0, right_strength_balance=10.0, opposite_sign=False)
    too_weak = _feature_row(slope=0.0, pre_range=12.0, right_strength_balance=3.99, opposite_sign=True)
    exactly_threshold = _feature_row(slope=0.0, pre_range=12.0, right_strength_balance=4.0, opposite_sign=True)

    assert evaluate_canonical_filter("opp_right_dom_ge4", not_opposite) is False
    assert evaluate_canonical_filter("opp_right_dom_ge4", too_weak) is False
    assert evaluate_canonical_filter("opp_right_dom_ge4", exactly_threshold) is True


def test_evaluate_canonical_filter_supports_trend_ratio_range_thresholds() -> None:
    features = _feature_row(slope=0.0, pre_range=12.0, trend_ratio=0.24)
    assert evaluate_canonical_filter("range_lt_0_20", features) is False
    assert evaluate_canonical_filter("range_lt_0_25", features) is True
    assert evaluate_canonical_filter("range_lt_0_30", features) is True
    assert evaluate_canonical_filter("range_lt_0_35", features) is True


def test_range_lt_0_3_remains_backward_compatible() -> None:
    features = _feature_row(slope=0.0, pre_range=12.0, trend_ratio=0.29)
    runtime_spec = to_runtime_filter_spec("range_lt_0_3")
    assert evaluate_canonical_filter("range_lt_0_3", features) is True
    assert get_filter_family("range_lt_0_3") == "trend_ratio"
    assert runtime_spec is not None
    assert runtime_spec.filter_type == "trend_ratio"
    assert runtime_spec.operator == "lt"
    assert runtime_spec.threshold == 0.3
