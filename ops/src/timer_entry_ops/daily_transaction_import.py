from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any

from timer_entry_runtime.level_policy import UnitLevelDecision, decide_emergency_demotion, infer_level_from_sizing
from timer_entry_runtime.models import SettingConfig

from .config import OpsConfig
from .data_api import DataApi, text_param
from .monthly_unit_level_policy import (
    _apply_setting_level,
    _decision_from_log,
    _insert_decision_log,
    _mark_decision_log_applied,
    _record_value,
    _should_apply,
)
from .oanda_transactions import OandaImportError
from .oanda_transactions import fetch_latest_transaction_id, fetch_transactions_since_id


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _load_secret(client: Any, secret_name: str) -> dict[str, Any]:
    response = client.get_secret_value(SecretId=secret_name)
    if "SecretString" not in response:
        raise RuntimeError("Binary secret is not supported")
    return json.loads(response["SecretString"])


def _json_dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _first_text(*values: Any) -> str:
    for value in values:
        if value is not None and str(value) != "":
            return str(value)
    return ""


def _nested_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_closed_trade(transaction: dict[str, Any]) -> dict[str, Any]:
    trades_closed = transaction.get("tradesClosed")
    if isinstance(trades_closed, list) and trades_closed:
        first = trades_closed[0]
        return first if isinstance(first, dict) else {}
    return {}


def _trade_opened(transaction: dict[str, Any]) -> dict[str, Any]:
    return _nested_dict(transaction.get("tradeOpened"))


def _client_extensions(transaction: dict[str, Any]) -> dict[str, Any]:
    return _nested_dict(transaction.get("clientExtensions"))


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
            text_param("raw_json", _json_dumps(transaction)),
        ],
    )


def _normalized_transaction_values(transaction: dict[str, Any]) -> dict[str, str]:
    trade_opened = _trade_opened(transaction)
    closed_trade = _first_closed_trade(transaction)
    client_extensions = _client_extensions(transaction)
    return {
        "transaction_id": _text(transaction.get("id")),
        "account_id": _text(transaction.get("accountID")),
        "transaction_time": _first_text(transaction.get("time"), "1970-01-01T00:00:00Z"),
        "transaction_type": _text(transaction.get("type")),
        "order_id": _text(transaction.get("orderID")),
        "trade_id": _first_text(transaction.get("tradeID"), trade_opened.get("tradeID"), closed_trade.get("tradeID")),
        "batch_id": _text(transaction.get("batchID")),
        "instrument": _text(transaction.get("instrument")),
        "units": _text(transaction.get("units")),
        "price": _text(transaction.get("price")),
        "pl": _text(transaction.get("pl")),
        "financing": _text(transaction.get("financing")),
        "account_balance": _text(transaction.get("accountBalance")),
        "reason": _text(transaction.get("reason")),
        "client_ext_id": _first_text(client_extensions.get("id"), transaction.get("clientOrderID")),
        "client_ext_tag": _first_text(client_extensions.get("tag"), transaction.get("clientOrderTag")),
        "client_ext_comment": _first_text(client_extensions.get("comment"), transaction.get("clientOrderComment")),
    }


def _insert_normalized_transaction(data_api: DataApi, schema: str, transaction: dict[str, Any]) -> dict[str, str]:
    values = _normalized_transaction_values(transaction)
    data_api.execute(
        f"""
insert into {schema}.oanda_transactions_normalized (
  transaction_id,
  account_id,
  transaction_time,
  transaction_type,
  order_id,
  trade_id,
  batch_id,
  instrument,
  units,
  price,
  pl,
  financing,
  account_balance,
  reason,
  client_ext_id,
  client_ext_tag,
  client_ext_comment,
  raw_transaction_id_ref,
  ingested_at
)
values (
  :transaction_id,
  nullif(:account_id, ''),
  cast(:transaction_time as timestamptz),
  :transaction_type,
  nullif(:order_id, ''),
  nullif(:trade_id, ''),
  nullif(:batch_id, ''),
  nullif(:instrument, ''),
  nullif(:units, '')::numeric,
  nullif(:price, '')::numeric,
  nullif(:pl, '')::numeric,
  nullif(:financing, '')::numeric,
  nullif(:account_balance, '')::numeric,
  nullif(:reason, ''),
  nullif(:client_ext_id, ''),
  nullif(:client_ext_tag, ''),
  nullif(:client_ext_comment, ''),
  :transaction_id,
  now()
)
on conflict (transaction_id) do update set
  transaction_time = excluded.transaction_time,
  account_id = excluded.account_id,
  transaction_type = excluded.transaction_type,
  order_id = excluded.order_id,
  trade_id = excluded.trade_id,
  batch_id = excluded.batch_id,
  instrument = excluded.instrument,
  units = excluded.units,
  price = excluded.price,
  pl = excluded.pl,
  financing = excluded.financing,
  account_balance = excluded.account_balance,
  reason = excluded.reason,
  client_ext_id = excluded.client_ext_id,
  client_ext_tag = excluded.client_ext_tag,
  client_ext_comment = excluded.client_ext_comment,
  ingested_at = excluded.ingested_at
""",
        [text_param(name, value) for name, value in values.items()],
    )
    return values


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


def _matching_oanda_where() -> str:
    return """
where (
  nullif(:trade_id, '') is not null and oanda_trade_id = nullif(:trade_id, '')
) or (
  nullif(:order_id, '') is not null and oanda_order_id = nullif(:order_id, '')
)
"""


def _upsert_oanda_only_fact(data_api: DataApi, schema: str, values: dict[str, str], *, is_exit: bool) -> None:
    data_api.execute(
        f"""
insert into {schema}.runtime_oanda_event_fact (
  fact_event_id,
  correlation_id,
  setting_id,
  strategy_id,
  slot_id,
  setting_labels,
  trade_date_local,
  market_tz,
  instrument,
  side,
  units,
  oanda_order_id,
  oanda_trade_id,
  oanda_client_id,
  entry_transaction_id,
  exit_transaction_id,
  entry_at,
  exit_at,
  entry_price,
  exit_price,
  pnl_jpy,
  account_balance,
  decision,
  reason,
  match_status,
  status,
  created_at,
  updated_at,
  synced_at
)
values (
  :fact_event_id,
  nullif(:correlation_id, ''),
  :setting_id,
  nullif(:strategy_id, ''),
  nullif(:slot_id, ''),
  '[]'::jsonb,
  null,
  null,
  nullif(:instrument, ''),
  null,
  nullif(:units, '')::numeric,
  nullif(:order_id, ''),
  nullif(:trade_id, ''),
  nullif(:client_ext_id, ''),
  nullif(:entry_transaction_id, ''),
  nullif(:exit_transaction_id, ''),
  nullif(:entry_at, '')::timestamptz,
  nullif(:exit_at, '')::timestamptz,
  nullif(:entry_price, '')::numeric,
  nullif(:exit_price, '')::numeric,
  nullif(:pl, '')::numeric,
  nullif(:account_balance, '')::numeric,
  'oanda_only',
  nullif(:reason, ''),
  'oanda_only',
  'oanda_only',
  cast(:created_at as timestamptz),
  cast(:updated_at as timestamptz),
  now()
)
on conflict (fact_event_id) do update set
  oanda_order_id = excluded.oanda_order_id,
  oanda_trade_id = excluded.oanda_trade_id,
  oanda_client_id = excluded.oanda_client_id,
  entry_transaction_id = coalesce(excluded.entry_transaction_id, {schema}.runtime_oanda_event_fact.entry_transaction_id),
  exit_transaction_id = coalesce(excluded.exit_transaction_id, {schema}.runtime_oanda_event_fact.exit_transaction_id),
  entry_at = coalesce(excluded.entry_at, {schema}.runtime_oanda_event_fact.entry_at),
  exit_at = coalesce(excluded.exit_at, {schema}.runtime_oanda_event_fact.exit_at),
  entry_price = coalesce(excluded.entry_price, {schema}.runtime_oanda_event_fact.entry_price),
  exit_price = coalesce(excluded.exit_price, {schema}.runtime_oanda_event_fact.exit_price),
  pnl_jpy = coalesce(excluded.pnl_jpy, {schema}.runtime_oanda_event_fact.pnl_jpy),
  account_balance = coalesce(excluded.account_balance, {schema}.runtime_oanda_event_fact.account_balance),
  updated_at = excluded.updated_at,
  synced_at = excluded.synced_at
""",
        [
            text_param("fact_event_id", f"oanda#{values['transaction_id']}"),
            text_param("correlation_id", values["trade_id"]),
            text_param("setting_id", _first_text(values["client_ext_id"], "unknown_oanda_only")),
            text_param("strategy_id", values["client_ext_tag"]),
            text_param("slot_id", ""),
            text_param("instrument", values["instrument"]),
            text_param("units", values["units"]),
            text_param("order_id", values["order_id"]),
            text_param("trade_id", values["trade_id"]),
            text_param("client_ext_id", values["client_ext_id"]),
            text_param("entry_transaction_id", "" if is_exit else values["transaction_id"]),
            text_param("exit_transaction_id", values["transaction_id"] if is_exit else ""),
            text_param("entry_at", "" if is_exit else values["transaction_time"]),
            text_param("exit_at", values["transaction_time"] if is_exit else ""),
            text_param("entry_price", "" if is_exit else values["price"]),
            text_param("exit_price", values["price"] if is_exit else ""),
            text_param("pl", values["pl"] if is_exit else ""),
            text_param("account_balance", values["account_balance"]),
            text_param("reason", values["reason"]),
            text_param("created_at", values["transaction_time"]),
            text_param("updated_at", values["transaction_time"]),
        ],
    )


def _update_fact_from_oanda_transaction(
    data_api: DataApi,
    schema: str,
    transaction: dict[str, Any],
    values: dict[str, str],
) -> None:
    is_exit = bool(_first_closed_trade(transaction)) or values["pl"] != ""
    entry_assignments = """
  entry_transaction_id = coalesce(entry_transaction_id, :transaction_id),
  entry_at = coalesce(entry_at, cast(:transaction_time as timestamptz)),
  entry_price = coalesce(entry_price, nullif(:price, '')::numeric),
"""
    exit_assignments = """
  exit_transaction_id = coalesce(exit_transaction_id, :transaction_id),
  exit_at = coalesce(exit_at, cast(:transaction_time as timestamptz)),
  exit_price = coalesce(exit_price, nullif(:price, '')::numeric),
  pnl_jpy = coalesce(nullif(:pl, '')::numeric, pnl_jpy),
"""
    response = data_api.execute(
        f"""
update {schema}.runtime_oanda_event_fact
set
  oanda_order_id = coalesce(oanda_order_id, nullif(:order_id, '')),
  oanda_trade_id = coalesce(oanda_trade_id, nullif(:trade_id, '')),
  oanda_client_id = coalesce(oanda_client_id, nullif(:client_ext_id, '')),
  units = coalesce(nullif(:units, '')::numeric, units),
  account_balance = coalesce(nullif(:account_balance, '')::numeric, account_balance),
  {exit_assignments if is_exit else entry_assignments}
  match_status = case when match_status in ('decision_only', 'execution_only') then 'matched' else match_status end,
  synced_at = now()
{_matching_oanda_where()}
""",
        [
            text_param(name, values[name])
            for name in (
                "transaction_id",
                "transaction_time",
                "order_id",
                "trade_id",
                "client_ext_id",
                "units",
                "price",
                "pl",
                "account_balance",
            )
        ],
    )
    if int(response.get("numberOfRecordsUpdated", 0)) == 0:
        _upsert_oanda_only_fact(data_api, schema, values, is_exit=is_exit)


def _upsert_fact_from_execution(data_api: DataApi, schema: str, item: dict[str, Any]) -> None:
    execution_id = str(item["execution_id"])
    correlation_id = str(item.get("correlation_id") or item.get("trade_id") or execution_id)
    common_params = [
        text_param("execution_id", execution_id),
        text_param("correlation_id", correlation_id),
        text_param("setting_id", _text(item.get("setting_id"))),
        text_param("strategy_id", _text(item.get("strategy_id"))),
        text_param("slot_id", _text(item.get("slot_id"))),
        text_param("setting_labels", _json_dumps(item.get("setting_labels", []))),
        text_param("trade_date_local", _text(item.get("trade_date_local"))),
        text_param("market_tz", _text(item.get("market_tz"))),
        text_param("instrument", _text(item.get("instrument"))),
        text_param("side", _text(item.get("side"))),
        text_param("units", _text(item.get("units"))),
        text_param("sizing_basis", _text(item.get("sizing_basis"))),
        text_param("account_balance", _text(item.get("balance"))),
        text_param("effective_margin_ratio", _text(item.get("effective_margin_ratio"))),
        text_param("estimated_margin_ratio_after_entry", _text(item.get("estimated_margin_ratio_after_entry"))),
        text_param("margin_price", _text(item.get("margin_price"))),
        text_param("margin_price_side", _text(item.get("margin_price_side"))),
        text_param("requested_entry_time_local", _text(item.get("requested_entry_time_local"))),
        text_param("requested_entry_time_utc", _text(item.get("requested_entry_time_utc"))),
        text_param("oanda_order_id", _text(item.get("oanda_order_id"))),
        text_param("oanda_trade_id", _text(item.get("oanda_trade_id"))),
        text_param("oanda_client_id", _text(item.get("oanda_client_id"))),
        text_param("entry_at", _text(item.get("entry_filled_at"))),
        text_param("entry_price", _text(item.get("entry_price"))),
        text_param("status", _text(item.get("status"))),
        text_param("created_at", _first_text(item.get("created_at"), item.get("requested_entry_time_utc"), _utc_now().isoformat())),
        text_param("updated_at", _first_text(item.get("updated_at"), item.get("created_at"), _utc_now().isoformat())),
    ]
    response = data_api.execute(
        f"""
update {schema}.runtime_oanda_event_fact
set
  execution_id = :execution_id,
  setting_labels = cast(:setting_labels as jsonb),
  units = coalesce(nullif(:units, '')::numeric, units),
  sizing_basis = coalesce(nullif(:sizing_basis, ''), sizing_basis),
  account_balance = coalesce(nullif(:account_balance, '')::numeric, account_balance),
  effective_margin_ratio = coalesce(nullif(:effective_margin_ratio, '')::numeric, effective_margin_ratio),
  estimated_margin_ratio_after_entry = coalesce(nullif(:estimated_margin_ratio_after_entry, '')::numeric, estimated_margin_ratio_after_entry),
  margin_price = coalesce(nullif(:margin_price, '')::numeric, margin_price),
  margin_price_side = coalesce(nullif(:margin_price_side, ''), margin_price_side),
  requested_entry_time_local = coalesce(nullif(:requested_entry_time_local, ''), requested_entry_time_local),
  requested_entry_time_utc = coalesce(nullif(:requested_entry_time_utc, '')::timestamptz, requested_entry_time_utc),
  oanda_order_id = coalesce(nullif(:oanda_order_id, ''), oanda_order_id),
  oanda_trade_id = coalesce(nullif(:oanda_trade_id, ''), oanda_trade_id),
  oanda_client_id = coalesce(nullif(:oanda_client_id, ''), oanda_client_id),
  entry_at = coalesce(nullif(:entry_at, '')::timestamptz, entry_at),
  entry_price = coalesce(nullif(:entry_price, '')::numeric, entry_price),
  status = coalesce(nullif(:status, ''), status),
  match_status = case when match_status = 'decision_only' then 'matched' else match_status end,
  updated_at = cast(:updated_at as timestamptz),
  synced_at = now()
where correlation_id = :correlation_id
""",
        common_params,
    )
    if int(response.get("numberOfRecordsUpdated", 0)) > 0:
        return
    data_api.execute(
        f"""
insert into {schema}.runtime_oanda_event_fact (
  fact_event_id,
  correlation_id,
  execution_id,
  setting_id,
  strategy_id,
  slot_id,
  setting_labels,
  trade_date_local,
  market_tz,
  instrument,
  side,
  units,
  sizing_basis,
  account_balance,
  effective_margin_ratio,
  estimated_margin_ratio_after_entry,
  margin_price,
  margin_price_side,
  requested_entry_time_local,
  requested_entry_time_utc,
  oanda_order_id,
  oanda_trade_id,
  oanda_client_id,
  entry_at,
  entry_price,
  match_status,
  status,
  created_at,
  updated_at,
  synced_at
)
values (
  :execution_id,
  :correlation_id,
  :execution_id,
  :setting_id,
  nullif(:strategy_id, ''),
  nullif(:slot_id, ''),
  cast(:setting_labels as jsonb),
  nullif(:trade_date_local, ''),
  nullif(:market_tz, ''),
  nullif(:instrument, ''),
  nullif(:side, ''),
  nullif(:units, '')::numeric,
  nullif(:sizing_basis, ''),
  nullif(:account_balance, '')::numeric,
  nullif(:effective_margin_ratio, '')::numeric,
  nullif(:estimated_margin_ratio_after_entry, '')::numeric,
  nullif(:margin_price, '')::numeric,
  nullif(:margin_price_side, ''),
  nullif(:requested_entry_time_local, ''),
  nullif(:requested_entry_time_utc, '')::timestamptz,
  nullif(:oanda_order_id, ''),
  nullif(:oanda_trade_id, ''),
  nullif(:oanda_client_id, ''),
  nullif(:entry_at, '')::timestamptz,
  nullif(:entry_price, '')::numeric,
  'execution_only',
  nullif(:status, ''),
  cast(:created_at as timestamptz),
  cast(:updated_at as timestamptz),
  now()
)
on conflict (fact_event_id) do update set
  correlation_id = excluded.correlation_id,
  setting_labels = excluded.setting_labels,
  status = excluded.status,
  updated_at = excluded.updated_at,
  synced_at = excluded.synced_at
""",
        common_params,
    )


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
  oanda_trade_id,
  exit_at,
  exit_price,
  pnl_pips,
  pnl_jpy,
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
  nullif(:oanda_trade_id, ''),
  nullif(:exit_at, '')::timestamptz,
  nullif(:exit_price, '')::numeric,
  nullif(:pnl_pips, '')::numeric,
  nullif(:pnl_jpy, '')::numeric,
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
  oanda_trade_id = coalesce(excluded.oanda_trade_id, {schema}.runtime_oanda_event_fact.oanda_trade_id),
  exit_at = coalesce(excluded.exit_at, {schema}.runtime_oanda_event_fact.exit_at),
  exit_price = coalesce(excluded.exit_price, {schema}.runtime_oanda_event_fact.exit_price),
  pnl_pips = coalesce(excluded.pnl_pips, {schema}.runtime_oanda_event_fact.pnl_pips),
  pnl_jpy = coalesce(excluded.pnl_jpy, {schema}.runtime_oanda_event_fact.pnl_jpy),
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
            text_param("oanda_trade_id", _first_text(item.get("entry_trade_id"), item.get("oanda_trade_id"))),
            text_param("exit_at", str(item.get("created_at", item.get("actual_invoked_at_utc", ""))) if item.get("decision") == "exited" else ""),
            text_param("exit_price", _text(item.get("exit_price"))),
            text_param("pnl_pips", _text(item.get("pnl_pips"))),
            text_param("pnl_jpy", _text(item.get("pnl_jpy"))),
            text_param("created_at", str(item.get("created_at", item.get("actual_invoked_at_utc", _utc_now().isoformat())))),
            text_param("updated_at", str(item.get("created_at", item.get("actual_invoked_at_utc", _utc_now().isoformat())))),
        ],
    )


def _decision_month_from_event(event: dict[str, Any]) -> str:
    trade_date_local = str(event.get("trade_date_local") or "")
    if len(trade_date_local) >= 7:
        return trade_date_local[:7]
    created_at = str(event.get("created_at") or "")
    if len(created_at) >= 7:
        return created_at[:7]
    return _utc_now().strftime("%Y-%m")


def _select_unprocessed_kill_switch_events(data_api: DataApi, schema: str) -> list[dict[str, Any]]:
    response = data_api.execute(
        f"""
select
  f.fact_event_id,
  f.setting_id,
  f.trade_date_local,
  f.created_at::text,
  l.decision_log_id,
  l.applied,
  l.current_level,
  l.next_level,
  l.decision,
  l.decision_reason,
  l.current_units,
  l.threshold_jpy,
  l.cum_jpy_month,
  l.unit_basis,
  l.policy_name,
  l.policy_version
from {schema}.runtime_oanda_event_fact f
left join {schema}.unit_level_decision_log l
  on l.decision_log_id = concat('kill_switch#', f.fact_event_id)
where f.decision = 'skipped_kill_switch'
  and coalesce(l.applied, false) = false
order by f.created_at asc, f.fact_event_id asc
limit 100
"""
    )
    events: list[dict[str, Any]] = []
    for record in response.get("records", []):
        events.append(
            {
                "fact_event_id": _record_value(record, 0),
                "setting_id": _record_value(record, 1),
                "trade_date_local": _record_value(record, 2),
                "created_at": _record_value(record, 3),
                "decision_log_id": _record_value(record, 4),
                "applied": _record_value(record, 5),
                "current_level": _record_value(record, 6),
                "next_level": _record_value(record, 7),
                "decision": _record_value(record, 8),
                "decision_reason": _record_value(record, 9),
                "current_units": _record_value(record, 10),
                "threshold_jpy": _record_value(record, 11),
                "cum_jpy_month": _record_value(record, 12),
                "unit_basis": _record_value(record, 13),
                "policy_name": _record_value(record, 14),
                "policy_version": _record_value(record, 15),
            }
        )
    return events


def _get_setting(setting_table: Any, setting_id: str) -> SettingConfig | None:
    response = setting_table.get_item(Key={"setting_id": setting_id})
    item = response.get("Item")
    return SettingConfig.from_item(item) if isinstance(item, dict) else None


def _process_kill_switch_demotions(
    *,
    data_api: DataApi,
    schema: str,
    setting_table: Any,
    now_utc: datetime,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for event in _select_unprocessed_kill_switch_events(data_api, schema):
        fact_event_id = str(event.get("fact_event_id") or "")
        setting_id = str(event.get("setting_id") or "")
        if not fact_event_id or not setting_id:
            results.append({"status": "skipped_missing_event_fields", "fact_event_id": fact_event_id, "setting_id": setting_id})
            continue
        setting = _get_setting(setting_table, setting_id)
        if setting is None:
            results.append({"status": "skipped_missing_setting", "fact_event_id": fact_event_id, "setting_id": setting_id})
            continue
        decision_month = _decision_month_from_event(event)
        decision_log_id = f"kill_switch#{fact_event_id}"
        if not setting.enabled:
            if event.get("decision_log_id"):
                results.append(
                    {"status": "skipped_disabled_pending_log", "fact_event_id": fact_event_id, "setting_id": setting_id}
                )
                continue
            current_level = infer_level_from_sizing(
                unit_level=setting.unit_level,
                fixed_units=setting.fixed_units,
                size_scale_pct=setting.size_scale_pct,
            )
            decision = UnitLevelDecision(
                source="kill_switch",
                current_level=current_level,
                next_level=current_level,
                decision="keep",
                decision_reason="disabled_setting",
            )
            _insert_decision_log(
                data_api,
                schema,
                setting=setting,
                decision_month=decision_month,
                decision=decision,
                latest_equity_jpy=None,
                closed_trade_count=0,
                applied=False,
                duplicate=False,
                now_utc=now_utc,
                decision_log_id=decision_log_id,
            )
            _mark_decision_log_applied(data_api, schema, decision_log_id=decision_log_id, now_utc=now_utc)
            results.append({"status": "skipped_disabled_setting", "fact_event_id": fact_event_id, "setting_id": setting_id})
            continue

        if event.get("decision_log_id"):
            decision = _decision_from_log(event, source="kill_switch")
        else:
            current_level = infer_level_from_sizing(
                unit_level=setting.unit_level,
                fixed_units=setting.fixed_units,
                size_scale_pct=setting.size_scale_pct,
            )
            decision = decide_emergency_demotion(
                current_level=current_level,
                source="kill_switch",
                decision_reason="kill_switch_triggered",
            )
            _insert_decision_log(
                data_api,
                schema,
                setting=setting,
                decision_month=decision_month,
                decision=decision,
                latest_equity_jpy=None,
                closed_trade_count=0,
                applied=False,
                duplicate=False,
                now_utc=now_utc,
                decision_log_id=decision_log_id,
            )
        applied = _should_apply(setting, decision)
        if applied:
            _apply_setting_level(
                setting_table,
                setting=setting,
                decision=decision,
                decision_month=decision_month,
                now_utc=now_utc,
                updated_by="ops_kill_switch_unit_level_policy",
            )
        _mark_decision_log_applied(data_api, schema, decision_log_id=decision_log_id, now_utc=now_utc)
        results.append(
            {
                "status": "processed",
                "fact_event_id": fact_event_id,
                "setting_id": setting_id,
                "current_level": decision.current_level,
                "next_level": decision.next_level,
                "decision": decision.decision,
                "decision_reason": decision.decision_reason,
                "applied": applied,
            }
        )
    return results


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
    setting_table = dynamodb.Table(config.setting_config_table_name)

    last_transaction_id = _read_last_transaction_id(data_api, config.main_schema)
    imported_transactions = 0
    normalized_transactions = 0
    normalized_transaction_values: list[tuple[dict[str, Any], dict[str, str]]] = []
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
                normalized_values = _insert_normalized_transaction(data_api, config.main_schema, transaction)
                normalized_transaction_values.append((transaction, normalized_values))
                imported_transactions += 1
                normalized_transactions += 1
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
    execution_items = _scan_table_since(dynamodb.Table(config.execution_log_table_name), since_utc)
    for item in execution_items:
        _upsert_fact_from_execution(data_api, config.main_schema, item)
    for transaction, normalized_values in normalized_transaction_values:
        _update_fact_from_oanda_transaction(data_api, config.main_schema, transaction, normalized_values)
    kill_switch_demotion_results = _process_kill_switch_demotions(
        data_api=data_api,
        schema=config.main_schema,
        setting_table=setting_table,
        now_utc=_utc_now(),
    )

    return {
        "status": "ok",
        "imported_transactions": imported_transactions,
        "normalized_transactions": normalized_transactions,
        "decision_log_items": len(decision_items),
        "execution_log_items": len(execution_items),
        "kill_switch_demotions": len(kill_switch_demotion_results),
        "kill_switch_demotions_applied": sum(1 for result in kill_switch_demotion_results if result.get("applied")),
        "last_transaction_id": latest_transaction_id,
        "bootstrapped_cursor": bootstrapped_cursor,
        "reset_invalid_cursor": reset_invalid_cursor,
    }
