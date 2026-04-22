from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from timer_entry.filters import parse_volatility_filter_label
from timer_entry.schemas import QualifyPromotionResult, StrategySetting

from .level_policy import POLICY_NAME, POLICY_VERSION, infer_level_from_sizing


def _load_payload(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("qualify result must be a JSON object")
    return payload


def _setting_from_result(payload: dict[str, Any]) -> tuple[StrategySetting, dict[str, object], QualifyPromotionResult]:
    result = QualifyPromotionResult.from_dict(payload)
    result.assert_promotable()
    return (
        result.to_strategy_setting(),
        {
            "source_result_type": result.result_type,
            "source_result_id": result.result_id,
            "source_params_files": result.source_params_files,
            "source_output_dirs": result.source_output_dirs,
            "selected_target_maintenance_margin_pct": result.selected_target_maintenance_margin_pct,
            "selected_risk_fraction": result.selected_risk_fraction,
            "final_equity_jpy": result.final_equity_jpy,
            "annualized_pips": result.annualized_pips,
            "cagr": result.cagr,
            "trade_rate": result.trade_rate,
            "gross_pips": result.gross_pips,
            "in_gross_pips": result.in_gross_pips,
            "out_gross_pips": result.out_gross_pips,
            "win_rate": result.win_rate,
            "evidence": result.evidence,
        },
        result,
    )


def _read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object is required: {path}")
    return payload


def _source_metadata_payloads(result_path: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[Path] = []
    source_output_dirs = payload.get("source_output_dirs")
    if isinstance(source_output_dirs, dict):
        for key in ("E004", "E005-E008"):
            raw_dir = source_output_dirs.get(key)
            if isinstance(raw_dir, str) and raw_dir:
                source_dir = Path(raw_dir)
                candidates.append(source_dir / "metadata.json")
                candidates.append(source_dir / "suite_metadata.json")
                if not source_dir.is_absolute():
                    candidates.append(result_path.parent / source_dir / "metadata.json")
                    candidates.append(result_path.parent / source_dir / "suite_metadata.json")

    payloads: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        metadata = _read_json_if_exists(candidate)
        if metadata is not None:
            payloads.append(metadata)
    return payloads


def _threshold_from_metadata(label: str, metadata: dict[str, Any]) -> float | None:
    threshold_metadata = metadata.get("threshold_metadata")
    if isinstance(threshold_metadata, dict):
        label_meta = threshold_metadata.get(label)
        if isinstance(label_meta, dict):
            raw = label_meta.get("resolved_pre_range_threshold")
            if raw is not None:
                return float(raw)
    raw_threshold = metadata.get("pre_range_threshold")
    if raw_threshold is not None:
        return float(raw_threshold)
    return None


def _resolve_pre_range_threshold(
    *,
    result_path: Path,
    payload: dict[str, Any],
    filter_labels: tuple[str, ...],
) -> float | None:
    volatility_labels = [label for label in filter_labels if parse_volatility_filter_label(label) is not None]
    if not volatility_labels:
        return None

    thresholds: set[float] = set()
    for label in volatility_labels:
        threshold = _threshold_from_metadata(label, payload)
        if threshold is None:
            for metadata in _source_metadata_payloads(result_path, payload):
                threshold = _threshold_from_metadata(label, metadata)
                if threshold is not None:
                    break
        if threshold is None:
            raise ValueError(
                f"pre_range_threshold is required for {label}; "
                "include threshold_metadata/pre_range_threshold in the qualify result or source metadata"
            )
        thresholds.add(float(threshold))

    if len(thresholds) > 1:
        raise ValueError(f"multiple pre_range thresholds in one runtime setting are not supported: {sorted(thresholds)}")
    return next(iter(thresholds))


def promote_qualify_result_to_runtime_config(
    path: str | Path,
    *,
    setting_id: str | None = None,
    enabled: bool = False,
    fixed_units: int | None = 10,
    margin_ratio_target: float | None = None,
    size_scale_pct: float | None = None,
    kill_switch_dd_pct: float | None = None,
    kill_switch_reference_balance_jpy: float | None = None,
    min_maintenance_margin_pct: float | None = None,
    max_concurrent_positions: int | None = 1,
) -> dict[str, object]:
    result_path = Path(path)
    payload = _load_payload(result_path)
    setting, execution_spec, result = _setting_from_result(payload)
    pre_range_threshold = _resolve_pre_range_threshold(
        result_path=result_path,
        payload=payload,
        filter_labels=setting.filter_labels,
    )

    if setting.tp_pips <= 0:
        raise ValueError("tp_pips must be greater than zero before promotion")
    if setting.sl_pips <= 0:
        raise ValueError("sl_pips must be greater than zero before promotion")
    if fixed_units is not None and fixed_units <= 0:
        raise ValueError("fixed_units must be greater than zero when provided")
    if fixed_units is None and margin_ratio_target is None:
        margin_ratio_target = result.selected_target_maintenance_margin_pct
    if fixed_units is None and margin_ratio_target is None:
        raise ValueError("margin_ratio_target is required when fixed_units is not provided")
    if margin_ratio_target is not None and margin_ratio_target <= 0:
        raise ValueError("margin_ratio_target must be greater than zero when provided")
    if size_scale_pct is not None and size_scale_pct <= 0:
        raise ValueError("size_scale_pct must be greater than zero when provided")
    if max_concurrent_positions is not None and max_concurrent_positions <= 0:
        raise ValueError("max_concurrent_positions must be greater than zero when provided")
    resolved_setting = setting.__class__(
        **{
            **setting.__dict__,
            "setting_id": setting_id or f"{setting.slot_id}_{setting.side}_runtime_v1",
            "enabled": enabled,
            "fixed_units": fixed_units,
            "margin_ratio_target": margin_ratio_target,
            "size_scale_pct": size_scale_pct,
            "kill_switch_dd_pct": kill_switch_dd_pct if kill_switch_dd_pct is not None else result.kill_switch_dd_pct,
            "kill_switch_reference_balance_jpy": kill_switch_reference_balance_jpy
            if kill_switch_reference_balance_jpy is not None
            else result.initial_capital_jpy,
            "min_maintenance_margin_pct": min_maintenance_margin_pct
            if min_maintenance_margin_pct is not None
            else result.min_maintenance_margin_pct,
            "max_concurrent_positions": max_concurrent_positions,
            "pre_range_threshold": pre_range_threshold,
            "execution_spec": {
                **execution_spec,
                "pre_range_threshold": pre_range_threshold,
                "source_file": str(path),
            },
        }
    )
    runtime_config = resolved_setting.to_runtime_json_dict()
    runtime_config["unit_level"] = infer_level_from_sizing(
        unit_level=None,
        fixed_units=fixed_units,
        size_scale_pct=size_scale_pct,
    )
    runtime_config["unit_level_policy_name"] = POLICY_NAME
    runtime_config["unit_level_policy_version"] = POLICY_VERSION
    runtime_config["unit_level_updated_at"] = None
    runtime_config["unit_level_updated_by"] = "promotion"
    runtime_config["unit_level_decision_month"] = None
    if not runtime_config.get("filter_spec_json") and tuple(setting.filter_labels) != ("all",):
        raise ValueError("filter_labels could not be converted to runtime filter_spec_json")
    return runtime_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Promote qualify result to runtime setting_config JSON.")
    parser.add_argument("--result-file", required=True)
    parser.add_argument("--out-file", required=True)
    parser.add_argument("--setting-id")
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--fixed-units", type=int, default=10)
    parser.add_argument("--use-margin-ratio", action="store_true")
    parser.add_argument("--margin-ratio-target", type=float)
    parser.add_argument("--size-scale-pct", type=float)
    parser.add_argument("--kill-switch-dd-pct", type=float)
    parser.add_argument("--kill-switch-reference-balance-jpy", type=float)
    parser.add_argument("--min-maintenance-margin-pct", type=float)
    parser.add_argument("--max-concurrent-positions", type=int, default=1)
    args = parser.parse_args(argv)

    runtime_config = promote_qualify_result_to_runtime_config(
        args.result_file,
        setting_id=args.setting_id,
        enabled=args.enabled,
        fixed_units=(None if args.use_margin_ratio else args.fixed_units),
        margin_ratio_target=args.margin_ratio_target,
        size_scale_pct=args.size_scale_pct,
        kill_switch_dd_pct=args.kill_switch_dd_pct,
        kill_switch_reference_balance_jpy=args.kill_switch_reference_balance_jpy,
        min_maintenance_margin_pct=args.min_maintenance_margin_pct,
        max_concurrent_positions=args.max_concurrent_positions,
    )
    out_path = Path(args.out_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(runtime_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
