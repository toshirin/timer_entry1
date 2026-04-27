from __future__ import annotations

from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from timer_entry.schemas import StrategySetting

from qualify.common.e005_e008 import parse_output_aliases
from qualify.common.params import E001Params, E002Params, E003Params, E004Params, E005E008Params
from qualify.common.e001 import _resolve_threshold_metadata


def test_e001_params_build_strategy_setting_with_dynamic_label() -> None:
    params = E001Params.from_dict(
        {
            "experiment_code": "E001",
            "variant_code": None,
            "slot_id": "tyo09",
            "side": "buy",
            "baseline": {
                "entry_clock_local": "09:25",
                "forced_exit_clock_local": "10:20",
                "tp_pips": 5,
                "sl_pips": 15,
                "filter_labels": ["all"],
            },
            "comparison_family": "pre_open_slope",
            "comparison_labels": ["all", "ge2"],
            "pass_stability_gate": True,
        }
    )
    setting = params.to_strategy_setting(comparison_label="ge2")
    assert setting.filter_labels == ("ge2",)
    assert setting.tp_pips == 5.0
    assert setting.sl_pips == 15.0


def test_baseline_exclude_windows_flow_to_strategy_setting() -> None:
    params = E001Params.from_dict(
        {
            "experiment_code": "E001",
            "variant_code": None,
            "slot_id": "lon12",
            "side": "buy",
            "baseline": {
                "entry_clock_local": "12:30",
                "forced_exit_clock_local": "13:25",
                "tp_pips": 10,
                "sl_pips": 20,
                "filter_labels": ["all"],
                "exclude_windows": ["us_uk_dst_mismatch"],
            },
            "comparison_family": "pre_open_slope",
            "comparison_labels": ["all", "ge2"],
            "pass_stability_gate": True,
        }
    )
    setting = params.to_strategy_setting(comparison_label="ge2")
    assert params.baseline.exclude_windows == ("us_uk_dst_mismatch",)
    assert setting.exclude_windows == ("us_uk_dst_mismatch",)


def test_strategy_setting_runtime_config_uses_explicit_execution_spec_exclude_windows() -> None:
    setting = StrategySetting(
        setting_id="lon12_buy_test",
        slot_id="lon12",
        side="buy",
        market_tz="Europe/London",
        entry_clock_local="12:30",
        forced_exit_clock_local="13:25",
        tp_pips=10,
        sl_pips=20,
        filter_labels=("all",),
        exclude_windows=("us_uk_dst_mismatch",),
        execution_spec={"exclude_windows": []},
    )

    runtime_config = setting.to_runtime_config()
    execution_spec = json.loads(runtime_config.execution_spec_json or "{}")

    assert execution_spec["exclude_windows"] == []


def test_e001_resolves_pre_range_percentile_threshold_metadata() -> None:
    metadata = _resolve_threshold_metadata(
        ("all", "vol_ge_p60", "vol_ge_p70"),
        [
            {"pre_range_pips": 10.0},
            {"pre_range_pips": 20.0},
            {"pre_range_pips": 30.0},
            {"pre_range_pips": 40.0},
            {"pre_range_pips": 50.0},
        ],
    )
    assert metadata["vol_ge_p60"]["resolved_pre_range_threshold"] == 34.0
    assert metadata["vol_ge_p60"]["resolved_percentile"] == 60
    assert metadata["vol_ge_p60"]["threshold_source"] == "global_pre_range_percentile"
    assert metadata["vol_ge_p70"]["resolved_pre_range_threshold"] == 38.0


def test_e001_resolves_trend_ratio_label_threshold_metadata() -> None:
    metadata = _resolve_threshold_metadata(("range_lt_0_20", "range_lt_0_35"), [])
    assert metadata["range_lt_0_20"]["resolved_threshold"] == 0.2
    assert metadata["range_lt_0_20"]["resolved_pre_range_threshold"] is None
    assert metadata["range_lt_0_20"]["resolved_percentile"] is None
    assert metadata["range_lt_0_20"]["threshold_source"] == "label_threshold"
    assert metadata["range_lt_0_35"]["resolved_threshold"] == 0.35


def test_e002_params_build_strategy_setting_with_baseline_filter() -> None:
    params = E002Params.from_dict(
        {
            "experiment_code": "E002",
            "variant_code": None,
            "slot_id": "lon08",
            "side": "buy",
            "baseline": {
                "entry_clock_local": "08:40",
                "forced_exit_clock_local": "09:35",
                "tp_pips": 10,
                "sl_pips": 15,
                "filter_labels": ["vol_ge_p70"],
            },
            "tp_values": [10, 15, 20],
            "sl_values": [10, 15],
            "pass_stability_gate": True,
        }
    )
    setting = params.to_strategy_setting(tp_pips=15.0, sl_pips=10.0, pre_range_threshold=12.5)
    assert setting.filter_labels == ("vol_ge_p70",)
    assert setting.tp_pips == 15.0
    assert setting.sl_pips == 10.0
    assert setting.pre_range_threshold == 12.5
    assert params.comparison_label(tp_pips=15.0, sl_pips=10.0) == "tp15_sl10"


def test_e003_params_build_strategy_setting_with_forced_exit_grid() -> None:
    params = E003Params.from_dict(
        {
            "experiment_code": "E003",
            "variant_code": "E003A",
            "slot_id": "tyo10",
            "side": "sell",
            "baseline": {
                "entry_clock_local": "10:10",
                "forced_exit_clock_local": "11:05",
                "tp_pips": 20,
                "sl_pips": 5,
                "filter_labels": ["all"],
            },
            "forced_exit_values": ["10:35", "10:45", "11:05"],
            "pass_stability_gate": True,
        }
    )
    setting = params.to_strategy_setting(forced_exit_clock_local="10:45", pre_range_threshold=8.0)
    assert setting.filter_labels == ("all",)
    assert setting.tp_pips == 20.0
    assert setting.sl_pips == 5.0
    assert setting.forced_exit_clock_local == "10:45"
    assert setting.pre_range_threshold == 8.0
    assert params.comparison_label(forced_exit_clock_local="10:45") == "fx1045"


def test_e004_params_build_strategy_setting_and_runtime_fields() -> None:
    params = E004Params.from_dict(
        {
            "experiment_code": "E004",
            "variant_code": None,
            "slot_id": "lon08",
            "side": "buy",
            "baseline": {
                "entry_clock_local": "08:40",
                "forced_exit_clock_local": "09:45",
                "tp_pips": 10,
                "sl_pips": 30,
                "filter_labels": ["vol_ge_p70"],
            },
            "pass_stability_gate": True,
            "slippage_mode": "fixed",
            "fixed_slippage_pips": 0.2,
            "entry_delay_seconds": 1,
        }
    )
    setting = params.to_strategy_setting(pre_range_threshold=15.0)
    assert setting.filter_labels == ("vol_ge_p70",)
    assert setting.tp_pips == 10.0
    assert setting.sl_pips == 30.0
    assert setting.forced_exit_clock_local == "09:45"
    assert setting.pre_range_threshold == 15.0
    assert params.comparison_label() == "buy0840_vol_ge_p70_tp10_sl30_fx0945"


def test_e005_e008_params_convert_to_e004_baseline() -> None:
    params = E005E008Params.from_dict(
        {
            "experiment_code": "E005-E008",
            "variant_code": None,
            "slot_id": "lon08",
            "side": "buy",
            "baseline": {
                "entry_clock_local": "08:40",
                "forced_exit_clock_local": "09:45",
                "tp_pips": 10,
                "sl_pips": 30,
                "filter_labels": ["vol_ge_p70"],
            },
            "pass_stability_gate": True,
            "selected_experiments": ["E005", "E007"],
            "slippage_values": [0.0, 0.2, 0.3],
            "entry_delay_values": [0, 30, 60],
            "target_maintenance_margin_candidates": [200, 150, 180],
            "kill_switch_dd_pct": -0.2,
            "initial_capital_jpy": 100000,
            "slippage_mode": "none",
            "fixed_slippage_pips": 0.0,
            "entry_delay_seconds": 0,
        }
    )
    baseline = params.to_e004_params()
    assert params.selected_experiments == ("E005", "E007")
    assert params.slippage_values == (0.0, 0.2, 0.3)
    assert params.entry_delay_values == (0, 30, 60)
    assert params.target_maintenance_margin_candidates == (150, 180, 200)
    assert baseline.experiment_code == "E004"
    assert baseline.comparison_label() == "buy0840_vol_ge_p70_tp10_sl30_fx0945"


def test_e005_e008_output_alias_parser() -> None:
    assert parse_output_aliases(["E007=E007A"]) == {"E007": "E007A"}
