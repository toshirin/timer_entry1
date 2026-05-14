from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "runtime" / "src"))

from timer_entry_runtime.level_policy import (
    DEFAULT_LEVELS,
    LEVEL0_FIXED_UNITS,
    MAX_LEVEL,
    UNIT_BASIS_MONTH_END,
    decide_emergency_demotion,
    decide_monthly_level,
    infer_level_from_sizing,
    level_sizing_fields,
    level_spec,
    threshold_jpy_for_units,
)


def test_default_levels_match_unit_level_policy() -> None:
    assert [(item.level, item.mode, item.fixed_units, item.size_scale_pct) for item in DEFAULT_LEVELS] == [
        (0, "fixed_units", 10, None),
        (1, "size_scale_pct", None, 0.1),
        (2, "size_scale_pct", None, 0.3),
        (3, "size_scale_pct", None, 1.0),
        (4, "size_scale_pct", None, 3.0),
        (5, "size_scale_pct", None, 10.0),
        (6, "size_scale_pct", None, 30.0),
        (7, "size_scale_pct", None, 100.0),
    ]


def test_level_sizing_fields_resolve_fixed_and_scale_levels() -> None:
    assert level_sizing_fields(0) == {"fixed_units": LEVEL0_FIXED_UNITS, "size_scale_pct": None}
    assert level_sizing_fields(3) == {"fixed_units": None, "size_scale_pct": 1.0}


def test_infer_level_from_existing_sizing_fields() -> None:
    assert infer_level_from_sizing(unit_level=None, fixed_units=10, size_scale_pct=None) == 0
    assert infer_level_from_sizing(unit_level=None, fixed_units=None, size_scale_pct=3.0) == 4
    assert infer_level_from_sizing(unit_level=2, fixed_units=10, size_scale_pct=None) == 2


def test_monthly_profit_above_threshold_promotes_one_level() -> None:
    decision = decide_monthly_level(
        current_level=3,
        current_units=1000,
        cum_jpy_month=101.0,
        labels=[],
    )

    assert decision.current_level == 3
    assert decision.next_level == 4
    assert decision.decision == "promote"
    assert decision.decision_reason == "monthly_profit_above_threshold"
    assert decision.threshold_jpy == 100.0
    assert decision.changed is True
    assert decision.unit_basis == UNIT_BASIS_MONTH_END


def test_monthly_loss_below_threshold_demotes_one_level() -> None:
    decision = decide_monthly_level(
        current_level=3,
        current_units=1000,
        cum_jpy_month=-101.0,
        labels=[],
    )

    assert decision.next_level == 2
    assert decision.decision == "demote"
    assert decision.decision_reason == "monthly_loss_below_threshold"


def test_monthly_pnl_inside_band_keeps_level() -> None:
    decision = decide_monthly_level(
        current_level=5,
        current_units=10000,
        cum_jpy_month=-300.0,
        labels=[],
    )

    assert decision.next_level == 5
    assert decision.decision == "keep"
    assert decision.decision_reason == "monthly_pnl_within_band"
    assert decision.threshold_jpy == 1000.0
    assert decision.changed is False


@pytest.mark.parametrize("cum_jpy_month", [100.0, -100.0])
def test_monthly_threshold_boundary_keeps_level(cum_jpy_month: float) -> None:
    decision = decide_monthly_level(
        current_level=3,
        current_units=1000,
        cum_jpy_month=cum_jpy_month,
        labels=[],
    )

    assert decision.next_level == 3
    assert decision.decision == "keep"
    assert decision.decision_reason == "monthly_pnl_within_band"


def test_watch_label_forces_level_zero_even_when_profit_is_large() -> None:
    decision = decide_monthly_level(
        current_level=4,
        current_units=3000,
        cum_jpy_month=10_000.0,
        labels=["fix10", "watch"],
    )

    assert decision.next_level == 0
    assert decision.decision == "force_level0_watch"
    assert decision.decision_reason == "watch_label"
    assert decision.changed is True


def test_max_level_profit_keeps_with_specific_reason() -> None:
    decision = decide_monthly_level(
        current_level=MAX_LEVEL,
        current_units=100000,
        cum_jpy_month=20_000.0,
        labels=[],
    )

    assert decision.next_level == MAX_LEVEL
    assert decision.decision == "keep"
    assert decision.decision_reason == "already_at_max_level_profit_above_threshold"


def test_min_level_loss_keeps_with_specific_reason() -> None:
    decision = decide_monthly_level(
        current_level=0,
        current_units=10,
        cum_jpy_month=-2.0,
        labels=[],
    )

    assert decision.next_level == 0
    assert decision.decision == "keep"
    assert decision.decision_reason == "already_at_min_level_loss_below_threshold"
    assert decision.threshold_jpy == 1.0


def test_emergency_demotion_demotes_one_level_immediately() -> None:
    decision = decide_emergency_demotion(
        current_level=4,
        source="kill_switch",
        decision_reason="kill_switch_triggered",
    )

    assert decision.source == "kill_switch"
    assert decision.current_level == 4
    assert decision.next_level == 3
    assert decision.decision == "demote"
    assert decision.decision_reason == "kill_switch_triggered"


def test_emergency_demotion_does_not_go_below_zero() -> None:
    decision = decide_emergency_demotion(
        current_level=0,
        source="runtime_anomaly",
        decision_reason="runtime_anomaly_detected",
    )

    assert decision.next_level == 0
    assert decision.decision == "keep"
    assert decision.decision_reason == "already_at_min_level_runtime_anomaly_detected"


def test_invalid_level_and_units_are_rejected() -> None:
    with pytest.raises(ValueError, match="unit level"):
        level_spec(8)
    with pytest.raises(ValueError, match="current_units"):
        threshold_jpy_for_units(0)
