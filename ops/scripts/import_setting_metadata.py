from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from timer_entry_ops.data_api import DataApi, text_param


VALID_SCHEMAS = {"ops_main", "ops_demo"}


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _json_dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _json_value(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return value


def _numeric_text(value: Any) -> str:
    if value is None or value == "":
        return ""
    return str(value)


def _bool_text(value: Any) -> str:
    return "true" if bool(value) else "false"


def _execution_spec(config: dict[str, Any]) -> dict[str, Any] | None:
    value = config.get("execution_spec_json")
    parsed = _json_value(value)
    return parsed if isinstance(parsed, dict) else None


def _config_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.rglob("*.json")))
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(path)
    return files


def _upsert_metadata(data_api: DataApi, schema: str, path: Path) -> None:
    config = json.loads(path.read_text())
    if not isinstance(config, dict):
        raise ValueError(f"{path} must contain a JSON object")
    setting_id = str(config.get("setting_id") or "")
    if not setting_id:
        raise ValueError(f"{path} does not contain setting_id")

    execution_spec = _execution_spec(config)
    filter_spec = _json_value(config.get("filter_spec_json"))
    labels = config.get("labels", [])
    if not isinstance(labels, list):
        labels = []

    data_api.execute(
        f"""
insert into {schema}.setting_metadata (
  setting_id,
  enabled,
  strategy_id,
  slot_id,
  setting_labels,
  market_session,
  market_tz,
  instrument,
  side,
  entry_clock_local,
  forced_exit_clock_local,
  fixed_units,
  margin_ratio_target,
  size_scale_pct,
  unit_level,
  unit_level_policy_name,
  unit_level_policy_version,
  unit_level_updated_at,
  unit_level_updated_by,
  unit_level_decision_month,
  tp_pips,
  sl_pips,
  research_label,
  kill_switch_dd_pct,
  kill_switch_reference_balance_jpy,
  min_maintenance_margin_pct,
  filter_spec_json,
  execution_spec_json,
  expected_trade_rate,
  expected_win_rate,
  expected_annualized_pips,
  expected_cagr,
  source_file,
  imported_at,
  raw_config
)
values (
  :setting_id,
  cast(:enabled as boolean),
  nullif(:strategy_id, ''),
  nullif(:slot_id, ''),
  cast(:setting_labels as jsonb),
  nullif(:market_session, ''),
  nullif(:market_tz, ''),
  nullif(:instrument, ''),
  nullif(:side, ''),
  nullif(:entry_clock_local, ''),
  nullif(:forced_exit_clock_local, ''),
  nullif(:fixed_units, '')::numeric,
  nullif(:margin_ratio_target, '')::numeric,
  nullif(:size_scale_pct, '')::numeric,
  nullif(:unit_level, '')::integer,
  nullif(:unit_level_policy_name, ''),
  nullif(:unit_level_policy_version, ''),
  nullif(:unit_level_updated_at, '')::timestamptz,
  nullif(:unit_level_updated_by, ''),
  nullif(:unit_level_decision_month, ''),
  nullif(:tp_pips, '')::numeric,
  nullif(:sl_pips, '')::numeric,
  nullif(:research_label, ''),
  nullif(:kill_switch_dd_pct, '')::numeric,
  nullif(:kill_switch_reference_balance_jpy, '')::numeric,
  nullif(:min_maintenance_margin_pct, '')::numeric,
  nullif(:filter_spec_json, '')::jsonb,
  nullif(:execution_spec_json, '')::jsonb,
  nullif(:expected_trade_rate, '')::numeric,
  nullif(:expected_win_rate, '')::numeric,
  nullif(:expected_annualized_pips, '')::numeric,
  nullif(:expected_cagr, '')::numeric,
  nullif(:source_file, ''),
  now(),
  cast(:raw_config as jsonb)
)
on conflict (setting_id) do update set
  enabled = excluded.enabled,
  strategy_id = excluded.strategy_id,
  slot_id = excluded.slot_id,
  setting_labels = excluded.setting_labels,
  market_session = excluded.market_session,
  market_tz = excluded.market_tz,
  instrument = excluded.instrument,
  side = excluded.side,
  entry_clock_local = excluded.entry_clock_local,
  forced_exit_clock_local = excluded.forced_exit_clock_local,
  fixed_units = excluded.fixed_units,
  margin_ratio_target = excluded.margin_ratio_target,
  size_scale_pct = excluded.size_scale_pct,
  unit_level = excluded.unit_level,
  unit_level_policy_name = excluded.unit_level_policy_name,
  unit_level_policy_version = excluded.unit_level_policy_version,
  unit_level_updated_at = excluded.unit_level_updated_at,
  unit_level_updated_by = excluded.unit_level_updated_by,
  unit_level_decision_month = excluded.unit_level_decision_month,
  tp_pips = excluded.tp_pips,
  sl_pips = excluded.sl_pips,
  research_label = excluded.research_label,
  kill_switch_dd_pct = excluded.kill_switch_dd_pct,
  kill_switch_reference_balance_jpy = excluded.kill_switch_reference_balance_jpy,
  min_maintenance_margin_pct = excluded.min_maintenance_margin_pct,
  filter_spec_json = excluded.filter_spec_json,
  execution_spec_json = excluded.execution_spec_json,
  expected_trade_rate = excluded.expected_trade_rate,
  expected_win_rate = excluded.expected_win_rate,
  expected_annualized_pips = excluded.expected_annualized_pips,
  expected_cagr = excluded.expected_cagr,
  source_file = excluded.source_file,
  imported_at = excluded.imported_at,
  raw_config = excluded.raw_config
""",
        [
            text_param("setting_id", setting_id),
            text_param("enabled", _bool_text(config.get("enabled"))),
            text_param("strategy_id", _text(config.get("strategy_id"))),
            text_param("slot_id", _text(config.get("slot_id"))),
            text_param("setting_labels", _json_dumps(labels)),
            text_param("market_session", _text(config.get("market_session"))),
            text_param("market_tz", _text(config.get("market_tz"))),
            text_param("instrument", _text(config.get("instrument"))),
            text_param("side", _text(config.get("side"))),
            text_param("entry_clock_local", _text(config.get("entry_clock_local"))),
            text_param("forced_exit_clock_local", _text(config.get("forced_exit_clock_local"))),
            text_param("fixed_units", _numeric_text(config.get("fixed_units"))),
            text_param("margin_ratio_target", _numeric_text(config.get("margin_ratio_target"))),
            text_param("size_scale_pct", _numeric_text(config.get("size_scale_pct"))),
            text_param("unit_level", _numeric_text(config.get("unit_level"))),
            text_param("unit_level_policy_name", _text(config.get("unit_level_policy_name"))),
            text_param("unit_level_policy_version", _text(config.get("unit_level_policy_version"))),
            text_param("unit_level_updated_at", _text(config.get("unit_level_updated_at"))),
            text_param("unit_level_updated_by", _text(config.get("unit_level_updated_by"))),
            text_param("unit_level_decision_month", _text(config.get("unit_level_decision_month"))),
            text_param("tp_pips", _numeric_text(config.get("tp_pips"))),
            text_param("sl_pips", _numeric_text(config.get("sl_pips"))),
            text_param("research_label", _text(config.get("research_label"))),
            text_param("kill_switch_dd_pct", _numeric_text(config.get("kill_switch_dd_pct"))),
            text_param(
                "kill_switch_reference_balance_jpy",
                _numeric_text(config.get("kill_switch_reference_balance_jpy")),
            ),
            text_param("min_maintenance_margin_pct", _numeric_text(config.get("min_maintenance_margin_pct"))),
            text_param("filter_spec_json", "" if filter_spec is None else _json_dumps(filter_spec)),
            text_param("execution_spec_json", "" if execution_spec is None else _json_dumps(execution_spec)),
            text_param("expected_trade_rate", _numeric_text((execution_spec or {}).get("trade_rate"))),
            text_param("expected_win_rate", _numeric_text((execution_spec or {}).get("win_rate"))),
            text_param("expected_annualized_pips", _numeric_text((execution_spec or {}).get("annualized_pips"))),
            text_param("expected_cagr", _numeric_text((execution_spec or {}).get("cagr"))),
            text_param("source_file", path.as_posix()),
            text_param("raw_config", _json_dumps(config)),
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Import runtime setting config JSON into ops setting_metadata.")
    parser.add_argument("paths", type=Path, nargs="+", help="runtime config JSON files or directories")
    parser.add_argument("--schema", default="ops_main", help="target schema: ops_main or ops_demo")
    args = parser.parse_args()

    schema = str(args.schema)
    if schema not in VALID_SCHEMAS:
        parser.error("--schema must be ops_main or ops_demo")

    import boto3

    session = boto3.session.Session(region_name=os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "ap-northeast-1")))
    data_api = DataApi(
        client=session.client("rds-data"),
        cluster_arn=_require_env("OPS_DB_CLUSTER_ARN"),
        secret_arn=_require_env("OPS_DB_SECRET_ARN"),
        database_name=os.getenv("OPS_DB_NAME", "timer_entry_ops"),
    )

    files = _config_files(args.paths)
    imported = 0
    for path in files:
        _upsert_metadata(data_api, schema, path)
        imported += 1
    print(f"imported {imported} setting metadata rows into {schema}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
