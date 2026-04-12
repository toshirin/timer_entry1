from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "runtime" / "src"))

from timer_entry_runtime.promotion import promote_qualify_params_to_runtime_config


def test_promote_e004_params_to_runtime_config(tmp_path: Path) -> None:
    params_path = tmp_path / "e004.json"
    params_path.write_text(
        json.dumps(
            {
                "experiment_code": "E004",
                "variant_code": None,
                "slot_id": "lon15",
                "side": "buy",
                "baseline": {
                    "entry_clock_local": "15:40",
                    "forced_exit_clock_local": "16:30",
                    "tp_pips": 15,
                    "sl_pips": 25,
                    "filter_labels": ["right_dom_ge4"],
                },
                "pass_stability_gate": True,
                "slippage_mode": "none",
                "fixed_slippage_pips": 0.0,
                "entry_delay_seconds": 0,
            }
        ),
        encoding="utf-8",
    )

    config = promote_qualify_params_to_runtime_config(params_path, setting_id="lon15_buy_runtime_v1")

    assert config["setting_id"] == "lon15_buy_runtime_v1"
    assert config["enabled"] is False
    assert config["market_tz"] == "Europe/London"
    assert config["trigger_bucket_entry"] == "ENTRY#Europe/London#1540"
    assert config["trigger_bucket_exit"] == "EXIT#Europe/London#1630"
    assert config["tp_pips"] == 15.0
    assert config["sl_pips"] == 25.0
    assert "right_strength_balance" in str(config["filter_spec_json"])

