from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from qualify.common.params import E001Params, E002Params


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
    setting = params.to_strategy_setting(tp_pips=15.0, sl_pips=10.0)
    assert setting.filter_labels == ("vol_ge_p70",)
    assert setting.tp_pips == 15.0
    assert setting.sl_pips == 10.0
    assert params.comparison_label(tp_pips=15.0, sl_pips=10.0) == "tp15_sl10"
