from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from timer_entry.features import FeatureComputationResult
from timer_entry.filters import (
    evaluate_canonical_filter,
    get_filter_family,
    parse_right_strength_filter_label,
    parse_slope_filter_label,
    parse_volatility_filter_label,
    to_runtime_filter_spec,
)


def _feature_row(*, slope: float, pre_range: float) -> FeatureComputationResult:
    return FeatureComputationResult(
        feature_available=True,
        missing_reason="",
        pre_open_slope_pips=slope,
        left_ret_pips=1.0,
        right_ret_pips=1.0,
        left_abs_pips=1.0,
        right_abs_pips=1.0,
        right_strength_balance_pips=1.0,
        pre_range_pips=pre_range,
        net_move_pips=slope,
        trend_ratio=0.5,
        same_sign=True,
        opposite_sign=False,
        left_stronger=False,
        right_stronger=False,
    )


def test_parse_slope_filter_label_supports_extended_thresholds() -> None:
    assert parse_slope_filter_label("ge2") == ("ge", 2.0)
    assert parse_slope_filter_label("le1_5") == ("le", 1.5)


def test_parse_volatility_filter_label_supports_percentiles() -> None:
    assert parse_volatility_filter_label("vol_ge_med") == ("ge", "med")
    assert parse_volatility_filter_label("vol_lt_p40") == ("lt", 40)


def test_parse_right_strength_filter_label_supports_quantiles() -> None:
    assert parse_right_strength_filter_label("rs_ge_q70") == ("ge", 70)


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

    rs_spec = to_runtime_filter_spec("rs_ge_q70", dynamic_threshold=2.5)
    assert rs_spec is not None
    assert rs_spec.mode == "right_strength_balance"
    assert rs_spec.threshold == 2.5


def test_get_filter_family_supports_extended_labels() -> None:
    assert get_filter_family("ge4") == "pre_open_slope"
    assert get_filter_family("vol_ge_p70") == "pre_range_regime"
    assert get_filter_family("rs_ge_q70") == "right_strength_balance_quantile"


def test_evaluate_canonical_filter_supports_right_strength_quantiles() -> None:
    features = _feature_row(slope=0.0, pre_range=12.0)
    assert evaluate_canonical_filter("rs_ge_q70", features, dynamic_threshold=0.5) is True
    assert evaluate_canonical_filter("rs_ge_q70", features, dynamic_threshold=1.5) is False
    with pytest.raises(ValueError):
        evaluate_canonical_filter("rs_ge_q70", features)
