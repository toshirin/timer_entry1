from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any

from .config import OpsConfig
from .data_api import DataApi, text_param
from .oanda_transactions import OandaImportError
from .oanda_transactions import fetch_latest_transaction_id, fetch_transactions_since_id


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _load_secret(client: Any, secret_name: str) -> dict[str, Any]:
    response = client.get_secret_value(SecretId=secret_name)
    if "SecretString" not in response:
        raise RuntimeError("Binary secret is not supported")
    return json.loads(response["SecretString"])


def _cursor_sql(schema: str) -> str:
    return f"""
select cursor_value
from {schema}.import_cursor
where cursor_name = 'oanda_last_transaction_id'
"""


def _read_last_transaction_id(data_api: DataApi, schema: str) -> str | None:
    response = data_api.execute(_cursor_sql(schema))
    records = response.get("records", [])
    if not records:
        return None
    value = records[0][0]
    return value.get("stringValue") if isinstance(value, dict) else None


def _write_last_transaction_id(data_api: DataApi, schema: str, transaction_id: str) -> None:
    data_api.execute(
        f"""
insert into {schema}.import_cursor (cursor_name, cursor_value, updated_at)
values ('oanda_last_transaction_id', :cursor_value, now())
on conflict (cursor_name)
do update set cursor_value = excluded.cursor_value, updated_at = excluded.updated_at
""",
        [text_param("cursor_value", transaction_id)],
    )


def _is_valid_transaction_id(value: str | None) -> bool:
    if value is None:
        return False
    return value.isdecimal() and int(value) > 0


def _is_invalid_transaction_id_error(exc: OandaImportError) -> bool:
    return "Invalid value specified for 'id'" in str(exc)


def _bootstrap_latest_cursor(
    *,
    data_api: DataApi,
    schema: str,
    oanda_secret: dict[str, Any],
) -> str:
    latest_transaction_id = fetch_latest_transaction_id(
        access_token=str(oanda_secret["access_token"]),
        account_id=str(oanda_secret["account_id"]),
        environment=str(oanda_secret.get("environment", "live")),
    )
    _write_last_transaction_id(data_api, schema, latest_transaction_id)
    return latest_transaction_id


def _insert_raw_transaction(data_api: DataApi, schema: str, transaction: dict[str, Any]) -> None:
    data_api.execute(
        f"""
insert into {schema}.oanda_transactions_raw (
  transaction_id,
  account_id,
  transaction_time,
  transaction_type,
  raw_json,
  ingested_at
)
values (
  :transaction_id,
  :account_id,
  cast(:transaction_time as timestamptz),
  :transaction_type,
  cast(:raw_json as jsonb),
  now()
)
on conflict (transaction_id) do update set
  raw_json = excluded.raw_json,
  ingested_at = excluded.ingested_at
""",
        [
            text_param("transaction_id", str(transaction["id"])),
            text_param("account_id", str(transaction.get("accountID", ""))),
            text_param("transaction_time", str(transaction.get("time", "1970-01-01T00:00:00Z"))),
            text_param("transaction_type", str(transaction.get("type", ""))),
            text_param("raw_json", json.dumps(transaction, separators=(",", ":"))),
        ],
    )


def _scan_table_since(table: Any, since_utc: datetime) -> list[dict[str, Any]]:
    # This is intentionally a scan in the first implementation. A runtime-side GSI
    # on created_at/day partition can replace it without changing the ops fact model.
    items: list[dict[str, Any]] = []
    scan_kwargs: dict[str, Any] = {}
    since_text = since_utc.isoformat()
    while True:
        response = table.scan(**scan_kwargs)
        for item in response.get("Items", []):
            created_at = str(item.get("created_at", item.get("actual_invoked_at_utc", "")))
            if created_at >= since_text:
                items.append(item)
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            return items
        scan_kwargs["ExclusiveStartKey"] = last_key


def _upsert_fact_from_decision(data_api: DataApi, schema: str, item: dict[str, Any]) -> None:
    decision_id = str(item["decision_id"])
    correlation_id = str(item.get("correlation_id") or item.get("trade_id") or decision_id)
    data_api.execute(
        f"""
insert into {schema}.runtime_oanda_event_fact (
  fact_event_id,
  correlation_id,
  decision_id,
  setting_id,
  strategy_id,
  slot_id,
  setting_labels,
  trade_date_local,
  market_tz,
  instrument,
  side,
  decision,
  reason,
  blocking_trade_id,
  blocking_setting_id,
  created_at,
  updated_at,
  synced_at,
  match_status
)
values (
  :fact_event_id,
  :correlation_id,
  :decision_id,
  :setting_id,
  :strategy_id,
  :slot_id,
  cast(:setting_labels as jsonb),
  :trade_date_local,
  :market_tz,
  :instrument,
  :side,
  :decision,
  :reason,
  :blocking_trade_id,
  :blocking_setting_id,
  cast(:created_at as timestamptz),
  cast(:updated_at as timestamptz),
  now(),
  'decision_only'
)
on conflict (fact_event_id) do update set
  correlation_id = excluded.correlation_id,
  setting_labels = excluded.setting_labels,
  decision = excluded.decision,
  reason = excluded.reason,
  blocking_trade_id = excluded.blocking_trade_id,
  blocking_setting_id = excluded.blocking_setting_id,
  updated_at = excluded.updated_at,
  synced_at = excluded.synced_at
""",
        [
            text_param("fact_event_id", decision_id),
            text_param("correlation_id", correlation_id),
            text_param("decision_id", decision_id),
            text_param("setting_id", str(item.get("setting_id", ""))),
            text_param("strategy_id", str(item.get("strategy_id", ""))),
            text_param("slot_id", str(item.get("slot_id", ""))),
            text_param("setting_labels", json.dumps(item.get("setting_labels", []), separators=(",", ":"))),
            text_param("trade_date_local", str(item.get("trade_date_local", ""))),
            text_param("market_tz", str(item.get("market_tz", ""))),
            text_param("instrument", str(item.get("instrument", ""))),
            text_param("side", str(item.get("side", ""))),
            text_param("decision", str(item.get("decision", ""))),
            text_param("reason", str(item.get("reason", ""))),
            text_param("blocking_trade_id", str(item.get("blocking_trade_id", ""))),
            text_param("blocking_setting_id", str(item.get("blocking_setting_id", ""))),
            text_param("created_at", str(item.get("created_at", item.get("actual_invoked_at_utc", _utc_now().isoformat())))),
            text_param("updated_at", str(item.get("created_at", item.get("actual_invoked_at_utc", _utc_now().isoformat())))),
        ],
    )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    import boto3

    config = OpsConfig.from_env()
    session = boto3.session.Session(region_name=config.aws_region)
    data_api = DataApi(
        client=session.client("rds-data"),
        cluster_arn=config.database_cluster_arn,
        secret_arn=config.database_secret_arn,
        database_name=config.database_name,
    )
    secrets = session.client("secretsmanager")
    dynamodb = session.resource("dynamodb")

    last_transaction_id = _read_last_transaction_id(data_api, config.main_schema)
    imported_transactions = 0
    latest_transaction_id = last_transaction_id
    bootstrapped_cursor = False
    reset_invalid_cursor = False
    oanda_secret = _load_secret(secrets, config.oanda_secret_name)
    if _is_valid_transaction_id(last_transaction_id):
        try:
            payload = fetch_transactions_since_id(
                access_token=str(oanda_secret["access_token"]),
                account_id=str(oanda_secret["account_id"]),
                environment=str(oanda_secret.get("environment", "live")),
                transaction_id=str(last_transaction_id),
            )
        except OandaImportError as exc:
            if not _is_invalid_transaction_id_error(exc):
                raise
            latest_transaction_id = _bootstrap_latest_cursor(
                data_api=data_api,
                schema=config.main_schema,
                oanda_secret=oanda_secret,
            )
            reset_invalid_cursor = True
            payload = None
        if payload is not None:
            for transaction in payload.get("transactions", []):
                _insert_raw_transaction(data_api, config.main_schema, transaction)
                imported_transactions += 1
            latest_transaction_id = str(payload.get("lastTransactionID", last_transaction_id))
            _write_last_transaction_id(data_api, config.main_schema, latest_transaction_id)
    else:
        latest_transaction_id = _bootstrap_latest_cursor(
            data_api=data_api,
            schema=config.main_schema,
            oanda_secret=oanda_secret,
        )
        bootstrapped_cursor = True
        reset_invalid_cursor = last_transaction_id is not None

    since_utc = _utc_now() - timedelta(hours=config.log_scan_lookback_hours)
    decision_items = _scan_table_since(dynamodb.Table(config.decision_log_table_name), since_utc)
    for item in decision_items:
        _upsert_fact_from_decision(data_api, config.main_schema, item)

    return {
        "status": "ok",
        "imported_transactions": imported_transactions,
        "decision_log_items": len(decision_items),
        "last_transaction_id": latest_transaction_id,
        "bootstrapped_cursor": bootstrapped_cursor,
        "reset_invalid_cursor": reset_invalid_cursor,
    }
