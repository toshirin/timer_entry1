from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from qualify.common.params import E004Params, E005E008Params


def _load_payload(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("qualify params must be a JSON object")
    return payload


def promote_qualify_params_to_runtime_config(
    path: str | Path,
    *,
    setting_id: str | None = None,
    enabled: bool = False,
    fixed_units: int | None = 10,
    margin_ratio_target: float | None = None,
    size_scale_pct: float | None = None,
    kill_switch_dd_pct: float | None = -0.2,
    kill_switch_reference_balance_jpy: float | None = 100_000.0,
    min_maintenance_margin_pct: float | None = 150.0,
    max_concurrent_positions: int | None = 1,
) -> dict[str, object]:
    payload = _load_payload(path)
    experiment_code = str(payload.get("experiment_code", ""))
    if experiment_code == "E004":
        params = E004Params.from_dict(payload)
    elif experiment_code == "E005-E008":
        params = E005E008Params.from_dict(payload).to_e004_params()
    else:
        raise ValueError("Only E004 or E005-E008 params can be promoted to runtime config")

    if not params.pass_stability_gate:
        raise ValueError("pass_stability_gate must be true before promotion")

    setting = params.to_strategy_setting()
    resolved_setting = setting.__class__(
        **{
            **setting.__dict__,
            "setting_id": setting_id or f"{setting.slot_id}_{setting.side}_runtime_v1",
            "enabled": enabled,
            "fixed_units": fixed_units,
            "margin_ratio_target": margin_ratio_target,
            "size_scale_pct": size_scale_pct,
            "kill_switch_dd_pct": kill_switch_dd_pct,
            "kill_switch_reference_balance_jpy": kill_switch_reference_balance_jpy,
            "min_maintenance_margin_pct": min_maintenance_margin_pct,
            "max_concurrent_positions": max_concurrent_positions,
            "execution_spec": {
                "source_experiment_code": experiment_code,
                "source_params_file": str(path),
                "slippage_mode": params.slippage_mode,
                "fixed_slippage_pips": params.fixed_slippage_pips,
                "entry_delay_seconds": params.entry_delay_seconds,
            },
        }
    )
    runtime_config = resolved_setting.to_runtime_json_dict()
    if not runtime_config.get("filter_spec_json") and tuple(setting.filter_labels) != ("all",):
        raise ValueError("filter_labels could not be converted to runtime filter_spec_json")
    return runtime_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Promote qualify params to runtime setting_config JSON.")
    parser.add_argument("--params-file", required=True)
    parser.add_argument("--out-file", required=True)
    parser.add_argument("--setting-id")
    parser.add_argument("--enabled", action="store_true")
    args = parser.parse_args(argv)

    runtime_config = promote_qualify_params_to_runtime_config(
        args.params_file,
        setting_id=args.setting_id,
        enabled=args.enabled,
    )
    out_path = Path(args.out_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(runtime_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
