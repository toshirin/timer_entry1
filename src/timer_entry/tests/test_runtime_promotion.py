from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "runtime" / "src"))

from timer_entry_runtime.promotion import promote_qualify_result_to_runtime_config


def test_promote_qualify_result_to_runtime_config(tmp_path: Path) -> None:
    result_path = tmp_path / "lon15_result.json"
    result_path.write_text(
        json.dumps(
            {
                "result_type": "qualify_promotion_result",
                "schema_version": 1,
                "result_id": "lon15_buy_v1",
                "slot_id": "lon15",
                "side": "buy",
                "market_tz": "Europe/London",
                "entry_clock_local": "15:40",
                "forced_exit_clock_local": "16:30",
                "tp_pips": 15,
                "sl_pips": 25,
                "filter_labels": ["right_dom_ge4"],
                "labels": ["news_sensitive", "london"],
                "pass_stability_gate": True,
                "e004_passed": True,
                "e005_passed": True,
                "e006_passed": True,
                "e007_passed": True,
                "e008_passed": True,
                "approved_for_runtime": True,
                "selected_target_maintenance_margin_pct": 150.0,
                "kill_switch_dd_pct": -0.2,
                "min_maintenance_margin_pct": 150.0,
                "initial_capital_jpy": 100000.0,
                "final_equity_jpy": 101000.0,
                "annualized_pips": 12.3,
                "cagr": 0.01,
                "trade_rate": 0.42,
                "gross_pips": 86.1,
                "in_gross_pips": 55.0,
                "out_gross_pips": 31.1,
                "win_rate": 0.54,
                "source_params_files": {
                    "E004": "qualify/params/lon15/e004.json",
                    "E005-E008": "qualify/params/lon15/e005-e008.json",
                },
                "source_output_dirs": {
                    "E004": "qualify/out/lon15/E004/latest",
                    "E005-E008": "qualify/out/lon15",
                },
                "evidence": {"E007": {"min_maintenance_margin_pct": 200.0}},
            }
        ),
        encoding="utf-8",
    )

    config = promote_qualify_result_to_runtime_config(result_path, setting_id="lon15_buy_runtime_v1")

    assert config["setting_id"] == "lon15_buy_runtime_v1"
    assert config["enabled"] is False
    assert config["market_tz"] == "Europe/London"
    assert config["trigger_bucket_entry"] == "ENTRY#Europe/London#1540"
    assert config["trigger_bucket_exit"] == "EXIT#Europe/London#1630"
    assert config["tp_pips"] == 15.0
    assert config["sl_pips"] == 25.0
    assert config["labels"] == ("news_sensitive", "london")
    assert config["kill_switch_dd_pct"] == -0.2
    assert config["kill_switch_reference_balance_jpy"] == 100000.0
    assert config["min_maintenance_margin_pct"] == 150.0
    assert config["unit_level"] == 0
    assert config["unit_level_policy_name"] == "unit_level_policy"
    assert config["unit_level_updated_by"] == "promotion"
    assert "right_strength_balance" in str(config["filter_spec_json"])
    assert "source_result_id" in str(config["execution_spec_json"])
    assert "selected_target_maintenance_margin_pct" in str(config["execution_spec_json"])
    assert "final_equity_jpy" in str(config["execution_spec_json"])


def test_promote_vol_percentile_filter_uses_source_threshold_metadata(tmp_path: Path) -> None:
    e004_dir = tmp_path / "qualify" / "out" / "tyo09" / "E004" / "latest"
    e004_dir.mkdir(parents=True)
    e004_dir.joinpath("metadata.json").write_text(
        json.dumps(
            {
                "pre_range_threshold": 20.5,
                "threshold_metadata": {
                    "vol_ge_p60": {
                        "resolved_pre_range_threshold": 20.5,
                        "resolved_percentile": 60,
                        "threshold_source": "global_pre_range_percentile",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result_path = tmp_path / "tyo09_sell_result.json"
    result_path.write_text(
        json.dumps(
            {
                "result_type": "qualify_promotion_result",
                "schema_version": 1,
                "result_id": "tyo09_sell_v1",
                "slot_id": "tyo09",
                "side": "sell",
                "market_tz": "Asia/Tokyo",
                "entry_clock_local": "09:35",
                "forced_exit_clock_local": "10:20",
                "tp_pips": 25,
                "sl_pips": 25,
                "filter_labels": ["vol_ge_p60"],
                "pass_stability_gate": True,
                "e004_passed": True,
                "e005_passed": True,
                "e006_passed": True,
                "e007_passed": True,
                "e008_passed": True,
                "approved_for_runtime": True,
                "selected_target_maintenance_margin_pct": 180.0,
                "kill_switch_dd_pct": -0.2,
                "min_maintenance_margin_pct": 150.0,
                "initial_capital_jpy": 100000.0,
                "final_equity_jpy": 101000.0,
                "annualized_pips": 12.3,
                "cagr": 0.01,
                "trade_rate": 0.42,
                "gross_pips": 86.1,
                "in_gross_pips": 55.0,
                "out_gross_pips": 31.1,
                "win_rate": 0.54,
                "source_output_dirs": {
                    "E004": str(e004_dir),
                },
                "source_params_files": {},
                "evidence": {},
            }
        ),
        encoding="utf-8",
    )

    config = promote_qualify_result_to_runtime_config(result_path, setting_id="tyo09_sell_runtime_v1")

    assert config["setting_id"] == "tyo09_sell_runtime_v1"
    assert '"filter_type":"pre_range_regime"' in str(config["filter_spec_json"])
    assert '"threshold":20.5' in str(config["filter_spec_json"])
    assert '"pre_range_threshold":20.5' in str(config["execution_spec_json"])


def test_promote_rejects_non_positive_tp_sl(tmp_path: Path) -> None:
    result_path = tmp_path / "result_bad.json"
    result_path.write_text(
        json.dumps(
            {
                "result_type": "qualify_promotion_result",
                "schema_version": 1,
                "result_id": "lon15_buy_bad",
                "slot_id": "lon15",
                "side": "buy",
                "market_tz": "Europe/London",
                "entry_clock_local": "15:40",
                "forced_exit_clock_local": "16:30",
                "tp_pips": 0,
                "sl_pips": 25,
                "filter_labels": ["right_dom_ge4"],
                "pass_stability_gate": True,
                "e004_passed": True,
                "e005_passed": True,
                "e006_passed": True,
                "e007_passed": True,
                "e008_passed": True,
                "approved_for_runtime": True,
                "kill_switch_dd_pct": -0.2,
                "min_maintenance_margin_pct": 150.0,
                "initial_capital_jpy": 100000.0,
            }
        ),
        encoding="utf-8",
    )

    try:
        promote_qualify_result_to_runtime_config(result_path, setting_id="lon15_buy_runtime_v1")
    except ValueError as exc:
        assert "tp_pips" in str(exc)
    else:
        raise AssertionError("expected non-positive tp_pips to be rejected")
