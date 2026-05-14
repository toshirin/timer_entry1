from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import json
from typing import Any
from zoneinfo import ZoneInfo

from timer_entry_runtime.level_policy import (
    MONTHLY_SOURCE,
    UNIT_BASIS_MONTH_END,
    UnitLevelDecision,
    decide_monthly_level,
    infer_level_from_sizing,
    level_sizing_fields,
)
from timer_entry_runtime.models import AccountSnapshot, OandaSecret, SettingConfig
from timer_entry_runtime.oanda_client import OandaClient
from timer_entry_runtime.sizing import compute_units

from .config import OpsConfig
from .data_api import DataApi, text_param


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _ddb_compatible(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _ddb_compatible(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_ddb_compatible(item) for item in value]
    return value


def _load_oanda_secret(client: Any, secret_name: str) -> OandaSecret:
    response = client.get_secret_value(SecretId=secret_name)
    if "SecretString" not in response:
        raise RuntimeError("Binary secret is not supported for Oanda credentials")
    payload = json.loads(response["SecretString"])
    return OandaSecret(
        access_token=str(payload["access_token"]),
        account_id=str(payload["account_id"]),
        environment=str(payload.get("environment", "live")),
    )


def _previous_month(now_utc: datetime, *, tz_name: str = "Asia/Tokyo") -> str:
    local_now = now_utc.astimezone(ZoneInfo(tz_name))
    year = local_now.year
    month = local_now.month - 1
    if month == 0:
        year -= 1
        month = 12
    return f"{year:04d}-{month:02d}"


def _month_bounds_utc(decision_month: str) -> tuple[str, str]:
    year_text, month_text = decision_month.split("-", maxsplit=1)
    year = int(year_text)
    month = int(month_text)
    if month < 1 or month > 12:
        raise ValueError(f"decision_month must be YYYY-MM: {decision_month}")
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start.isoformat(), end.isoformat()


def _record_value(record: list[dict[str, Any]], index: int) -> Any:
    value = record[index]
    if "isNull" in value and value["isNull"]:
        return None
    for key in ("stringValue", "longValue", "doubleValue", "booleanValue"):
        if key in value:
            return value[key]
    return None


def _monthly_realized_pnl(data_api: DataApi, schema: str, setting_id: str, decision_month: str) -> tuple[float, int]:
    month_start, month_end = _month_bounds_utc(decision_month)
    response = data_api.execute(
        f"""
select
  coalesce(sum(pnl_jpy), 0)::text as cum_jpy_month,
  count(*) filter (where pnl_jpy is not null) as closed_trade_count
from {schema}.runtime_oanda_event_fact
where setting_id = :setting_id
  and pnl_jpy is not null
  and coalesce(exit_at, updated_at, created_at) >= cast(:month_start as timestamptz)
  and coalesce(exit_at, updated_at, created_at) < cast(:month_end as timestamptz)
""",
        [
            text_param("setting_id", setting_id),
            text_param("month_start", month_start),
            text_param("month_end", month_end),
        ],
    )
    records = response.get("records", [])
    if not records:
        return 0.0, 0
    return float(_record_value(records[0], 0) or 0), int(_record_value(records[0], 1) or 0)


def _decision_log_id(setting_id: str, decision_month: str, source: str) -> str:
    return f"{source}#{decision_month}#{setting_id}"


def _read_existing_decision_log(
    data_api: DataApi,
    schema: str,
    *,
    setting_id: str | None = None,
    decision_month: str | None = None,
    source: str | None = None,
    decision_log_id: str | None = None,
) -> dict[str, Any] | None:
    if decision_log_id is None:
        if setting_id is None or decision_month is None or source is None:
            raise ValueError("setting_id, decision_month, and source are required without decision_log_id")
        decision_log_id = _decision_log_id(setting_id, decision_month, source)
    response = data_api.execute(
        f"""
select
  decision_log_id,
  applied,
  current_level,
  next_level,
  decision,
  decision_reason,
  current_units,
  threshold_jpy,
  cum_jpy_month,
  unit_basis,
  policy_name,
  policy_version
from {schema}.unit_level_decision_log
where decision_log_id = :decision_log_id
""",
        [text_param("decision_log_id", decision_log_id)],
    )
    records = response.get("records", [])
    if not records:
        return None
    record = records[0]
    return {
        "decision_log_id": _record_value(record, 0),
        "applied": bool(_record_value(record, 1)),
        "current_level": _record_value(record, 2),
        "next_level": _record_value(record, 3),
        "decision": _record_value(record, 4),
        "decision_reason": _record_value(record, 5),
        "current_units": _record_value(record, 6),
        "threshold_jpy": _record_value(record, 7),
        "cum_jpy_month": _record_value(record, 8),
        "unit_basis": _record_value(record, 9),
        "policy_name": _record_value(record, 10),
        "policy_version": _record_value(record, 11),
    }


def _decision_from_log(existing: dict[str, Any], *, source: str) -> UnitLevelDecision:
    return UnitLevelDecision(
        source=source,
        current_level=int(existing["current_level"]),
        next_level=int(existing["next_level"]),
        decision=str(existing["decision"]),  # type: ignore[arg-type]
        decision_reason=str(existing["decision_reason"]),
        current_units=int(existing["current_units"]) if existing.get("current_units") is not None else None,
        threshold_jpy=float(existing["threshold_jpy"]) if existing.get("threshold_jpy") is not None else None,
        cum_jpy_month=float(existing["cum_jpy_month"]) if existing.get("cum_jpy_month") is not None else None,
        unit_basis=str(existing["unit_basis"]) if existing.get("unit_basis") is not None else None,
        policy_name=str(existing.get("policy_name") or "unit_level_policy"),
        policy_version=str(existing.get("policy_version") or "2026-04-17"),
    )


def _mark_decision_log_applied(
    data_api: DataApi,
    schema: str,
    *,
    decision_log_id: str,
    now_utc: datetime,
) -> None:
    data_api.execute(
        f"""
update {schema}.unit_level_decision_log
set
  applied = true,
  applied_at = coalesce(applied_at, cast(:applied_at as timestamptz))
where decision_log_id = :decision_log_id
""",
        [
            text_param("decision_log_id", decision_log_id),
            text_param("applied_at", now_utc.isoformat()),
        ],
    )


def _insert_decision_log(
    data_api: DataApi,
    schema: str,
    *,
    setting: SettingConfig,
    decision_month: str,
    decision: UnitLevelDecision,
    latest_equity_jpy: float | None,
    closed_trade_count: int,
    applied: bool,
    duplicate: bool,
    now_utc: datetime,
    decision_log_id: str | None = None,
) -> None:
    data_api.execute(
        f"""
insert into {schema}.unit_level_decision_log (
  decision_log_id,
  setting_id,
  strategy_id,
  slot_id,
  instrument,
  market_session,
  decision_month,
  policy_name,
  policy_version,
  labels,
  source,
  current_level,
  next_level,
  current_units,
  threshold_jpy,
  cum_jpy_month,
  latest_equity_jpy,
  unit_basis,
  closed_trade_count,
  decision,
  decision_reason,
  applied,
  duplicate,
  applied_at,
  created_at
)
values (
  :decision_log_id,
  :setting_id,
  nullif(:strategy_id, ''),
  nullif(:slot_id, ''),
  nullif(:instrument, ''),
  nullif(:market_session, ''),
  :decision_month,
  :policy_name,
  :policy_version,
  cast(:labels as jsonb),
  :source,
  cast(:current_level as integer),
  cast(:next_level as integer),
  nullif(:current_units, '')::numeric,
  nullif(:threshold_jpy, '')::numeric,
  nullif(:cum_jpy_month, '')::numeric,
  nullif(:latest_equity_jpy, '')::numeric,
  nullif(:unit_basis, ''),
  cast(:closed_trade_count as integer),
  :decision,
  :decision_reason,
  cast(:applied as boolean),
  cast(:duplicate as boolean),
  nullif(:applied_at, '')::timestamptz,
  cast(:created_at as timestamptz)
)
on conflict (decision_log_id) do nothing
""",
        [
            text_param("decision_log_id", decision_log_id or _decision_log_id(setting.setting_id, decision_month, decision.source)),
            text_param("setting_id", setting.setting_id),
            text_param("strategy_id", setting.strategy_id),
            text_param("slot_id", setting.slot_id),
            text_param("instrument", setting.instrument),
            text_param("market_session", setting.market_session),
            text_param("decision_month", decision_month),
            text_param("policy_name", decision.policy_name),
            text_param("policy_version", decision.policy_version),
            text_param("labels", _json_dumps(setting.labels)),
            text_param("source", decision.source),
            text_param("current_level", str(decision.current_level)),
            text_param("next_level", str(decision.next_level)),
            text_param("current_units", _text(decision.current_units)),
            text_param("threshold_jpy", _text(decision.threshold_jpy)),
            text_param("cum_jpy_month", _text(decision.cum_jpy_month)),
            text_param("latest_equity_jpy", _text(latest_equity_jpy)),
            text_param("unit_basis", _text(decision.unit_basis)),
            text_param("closed_trade_count", str(closed_trade_count)),
            text_param("decision", decision.decision),
            text_param("decision_reason", decision.decision_reason),
            text_param("applied", _bool_text(applied)),
            text_param("duplicate", _bool_text(duplicate)),
            text_param("applied_at", now_utc.isoformat() if applied else ""),
            text_param("created_at", now_utc.isoformat()),
        ],
    )


def _scan_settings(setting_table: Any) -> list[SettingConfig]:
    items: list[dict[str, Any]] = []
    scan_kwargs: dict[str, Any] = {}
    while True:
        response = setting_table.scan(**scan_kwargs)
        items.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key
    return [SettingConfig.from_item(item) for item in items]


def _setting_for_level(setting: SettingConfig, level: int) -> SettingConfig:
    sizing_fields = level_sizing_fields(level)
    return replace(
        setting,
        fixed_units=sizing_fields["fixed_units"],  # type: ignore[arg-type]
        size_scale_pct=sizing_fields["size_scale_pct"],  # type: ignore[arg-type]
        unit_level=level,
    )


def _current_units(
    *,
    setting: SettingConfig,
    current_level: int,
    account: AccountSnapshot,
    oanda_client: OandaClient,
    price_cache: dict[str, Any],
) -> int:
    if current_level == 0:
        return 10
    effective_setting = _setting_for_level(setting, current_level)
    price = price_cache.get(setting.instrument)
    if price is None:
        price = oanda_client.get_price_snapshot(setting.instrument)
        price_cache[setting.instrument] = price
    return compute_units(setting=effective_setting, account=account, price=price).requested_units


def _should_apply(setting: SettingConfig, decision: UnitLevelDecision) -> bool:
    next_fields = level_sizing_fields(decision.next_level)
    next_size_scale_pct = next_fields["size_scale_pct"]
    current_size_scale_pct = setting.size_scale_pct
    size_scale_differs = (
        current_size_scale_pct is None
        if next_size_scale_pct is not None
        else current_size_scale_pct is not None
    )
    if current_size_scale_pct is not None and next_size_scale_pct is not None:
        size_scale_differs = abs(float(current_size_scale_pct) - float(next_size_scale_pct)) > 1e-12
    return (
        setting.unit_level != decision.next_level
        or setting.unit_level_policy_name != decision.policy_name
        or setting.unit_level_policy_version != decision.policy_version
        or setting.fixed_units != next_fields["fixed_units"]
        or size_scale_differs
    )


def _apply_recorded_decision(
    *,
    data_api: DataApi,
    schema: str,
    setting_table: Any,
    setting: SettingConfig,
    decision_month: str,
    decision: UnitLevelDecision,
    decision_log_id: str,
    now_utc: datetime,
    updated_by: str,
) -> bool:
    applied = _should_apply(setting, decision)
    if applied:
        _apply_setting_level(
            setting_table,
            setting=setting,
            decision=decision,
            decision_month=decision_month,
            now_utc=now_utc,
            updated_by=updated_by,
        )
    _sync_setting_metadata_level(
        data_api=data_api,
        schema=schema,
        decision=decision,
        decision_month=decision_month,
        setting_id=setting.setting_id,
        now_utc=now_utc,
        updated_by=updated_by,
    )
    _mark_decision_log_applied(data_api, schema, decision_log_id=decision_log_id, now_utc=now_utc)
    return applied


def _apply_setting_level(
    setting_table: Any,
    *,
    setting: SettingConfig,
    decision: UnitLevelDecision,
    decision_month: str,
    now_utc: datetime,
    updated_by: str = "ops_monthly_unit_level_policy",
) -> None:
    sizing_fields = level_sizing_fields(decision.next_level)
    setting_table.update_item(
        Key={"setting_id": setting.setting_id},
        UpdateExpression=(
            "SET unit_level = :unit_level, "
            "unit_level_policy_name = :policy_name, "
            "unit_level_policy_version = :policy_version, "
            "unit_level_updated_at = :updated_at, "
            "unit_level_updated_by = :updated_by, "
            "unit_level_decision_month = :decision_month, "
            "fixed_units = :fixed_units, "
            "size_scale_pct = :size_scale_pct, "
            "updated_at = :updated_at"
        ),
        ExpressionAttributeValues=_ddb_compatible(
            {
                ":unit_level": decision.next_level,
                ":policy_name": decision.policy_name,
                ":policy_version": decision.policy_version,
                ":updated_at": now_utc.isoformat(),
                ":updated_by": updated_by,
                ":decision_month": decision_month,
                ":fixed_units": sizing_fields["fixed_units"],
                ":size_scale_pct": sizing_fields["size_scale_pct"],
            }
        ),
    )


def _sync_setting_metadata_level(
    *,
    data_api: DataApi,
    schema: str,
    decision: UnitLevelDecision,
    decision_month: str,
    setting_id: str,
    now_utc: datetime,
    updated_by: str,
) -> None:
    sizing_fields = level_sizing_fields(decision.next_level)
    data_api.execute(
        f"""
update {schema}.setting_metadata
set
  unit_level = cast(:unit_level as integer),
  unit_level_policy_name = :policy_name,
  unit_level_policy_version = :policy_version,
  unit_level_updated_at = cast(:updated_at as timestamptz),
  unit_level_updated_by = :updated_by,
  unit_level_decision_month = :decision_month,
  fixed_units = nullif(:fixed_units, '')::numeric,
  size_scale_pct = nullif(:size_scale_pct, '')::numeric,
  imported_at = cast(:updated_at as timestamptz)
where setting_id = :setting_id
""",
        [
            text_param("setting_id", setting_id),
            text_param("unit_level", str(decision.next_level)),
            text_param("policy_name", decision.policy_name),
            text_param("policy_version", decision.policy_version),
            text_param("updated_at", now_utc.isoformat()),
            text_param("updated_by", updated_by),
            text_param("decision_month", decision_month),
            text_param("fixed_units", _text(sizing_fields["fixed_units"])),
            text_param("size_scale_pct", _text(sizing_fields["size_scale_pct"])),
        ],
    )


def process_setting(
    *,
    data_api: DataApi,
    schema: str,
    setting_table: Any,
    setting: SettingConfig,
    decision_month: str,
    account: AccountSnapshot,
    oanda_client: OandaClient,
    price_cache: dict[str, Any],
    now_utc: datetime,
) -> dict[str, Any]:
    existing = _read_existing_decision_log(
        data_api,
        schema,
        setting_id=setting.setting_id,
        decision_month=decision_month,
        source=MONTHLY_SOURCE,
    )
    if existing and existing["applied"]:
        decision = _decision_from_log(existing, source=MONTHLY_SOURCE)
        _sync_setting_metadata_level(
            data_api=data_api,
            schema=schema,
            decision=decision,
            decision_month=decision_month,
            setting_id=setting.setting_id,
            now_utc=now_utc,
            updated_by="ops_monthly_unit_level_policy",
        )
        return {
            "setting_id": setting.setting_id,
            "status": "duplicate_skipped",
            "decision_month": decision_month,
            "decision_reason": existing["decision_reason"],
            "metadata_synced": True,
        }
    if existing:
        decision = _decision_from_log(existing, source=MONTHLY_SOURCE)
        applied = _apply_recorded_decision(
            data_api=data_api,
            schema=schema,
            setting_table=setting_table,
            setting=setting,
            decision_month=decision_month,
            decision=decision,
            decision_log_id=str(existing["decision_log_id"]),
            now_utc=now_utc,
            updated_by="ops_monthly_unit_level_policy",
        )
        return {
            "setting_id": setting.setting_id,
            "status": "resumed_pending_log",
            "decision_month": decision_month,
            "current_level": decision.current_level,
            "next_level": decision.next_level,
            "decision": decision.decision,
            "decision_reason": decision.decision_reason,
            "applied": applied,
        }

    current_level = infer_level_from_sizing(
        unit_level=setting.unit_level,
        fixed_units=setting.fixed_units,
        size_scale_pct=setting.size_scale_pct,
    )
    current_units = _current_units(
        setting=setting,
        current_level=current_level,
        account=account,
        oanda_client=oanda_client,
        price_cache=price_cache,
    )
    cum_jpy_month, closed_trade_count = _monthly_realized_pnl(data_api, schema, setting.setting_id, decision_month)
    decision = decide_monthly_level(
        current_level=current_level,
        current_units=current_units,
        cum_jpy_month=cum_jpy_month,
        labels=setting.labels,
        unit_basis=UNIT_BASIS_MONTH_END,
    )
    applied = _should_apply(setting, decision)
    decision_log_id = _decision_log_id(setting.setting_id, decision_month, decision.source)
    _insert_decision_log(
        data_api,
        schema,
        setting=setting,
        decision_month=decision_month,
        decision=decision,
        latest_equity_jpy=account.balance,
        closed_trade_count=closed_trade_count,
        applied=False,
        duplicate=False,
        now_utc=now_utc,
        decision_log_id=decision_log_id,
    )
    if applied:
        _apply_setting_level(
            setting_table,
            setting=setting,
            decision=decision,
            decision_month=decision_month,
            now_utc=now_utc,
        )
    if applied:
        _sync_setting_metadata_level(
            data_api=data_api,
            schema=schema,
            decision=decision,
            decision_month=decision_month,
            setting_id=setting.setting_id,
            now_utc=now_utc,
            updated_by="ops_monthly_unit_level_policy",
        )
    _mark_decision_log_applied(data_api, schema, decision_log_id=decision_log_id, now_utc=now_utc)
    return {
        "setting_id": setting.setting_id,
        "status": "processed",
        "decision_month": decision_month,
        "current_level": decision.current_level,
        "next_level": decision.next_level,
        "decision": decision.decision,
        "decision_reason": decision.decision_reason,
        "applied": applied,
    }


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    import boto3

    config = OpsConfig.from_env()
    now_utc = _utc_now()
    decision_month = str(
        event.get("decision_month")
        or _previous_month(now_utc, tz_name=config.unit_level_decision_timezone)
    )

    session = boto3.session.Session(region_name=config.aws_region)
    data_api = DataApi(
        client=session.client("rds-data"),
        cluster_arn=config.database_cluster_arn,
        secret_arn=config.database_secret_arn,
        database_name=config.database_name,
    )
    secrets = session.client("secretsmanager")
    dynamodb = session.resource("dynamodb")
    setting_table = dynamodb.Table(config.setting_config_table_name)

    oanda_secret = _load_oanda_secret(secrets, config.oanda_secret_name)
    oanda_client = OandaClient(oanda_secret)
    account = oanda_client.get_account_snapshot()
    price_cache: dict[str, Any] = {}

    include_disabled = bool(event.get("include_disabled", False))
    settings = _scan_settings(setting_table)
    results: list[dict[str, Any]] = []
    for setting in settings:
        if not include_disabled and not setting.enabled:
            continue
        results.append(
            process_setting(
                data_api=data_api,
                schema=config.main_schema,
                setting_table=setting_table,
                setting=setting,
                decision_month=decision_month,
                account=account,
                oanda_client=oanda_client,
                price_cache=price_cache,
                now_utc=now_utc,
            )
        )

    return {
        "status": "ok",
        "decision_month": decision_month,
        "processed_settings": len(results),
        "applied_settings": sum(1 for result in results if result.get("applied")),
        "duplicate_skipped": sum(1 for result in results if result.get("status") == "duplicate_skipped"),
        "results": results,
    }
