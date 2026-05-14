from __future__ import annotations

"""
Backfill `runtime_oanda_event_fact.exit_transaction_id` and `exit_reason`.

Purpose:
- Fix old rows where `exit_transaction_id` incorrectly points to the entry fill.
- Derive `exit_reason` from the actual close-side Oanda ORDER_FILL transaction.

Default behavior is dry-run. It prints summary counts and sample rows only.
Actual updates happen only with `--apply`.

Local example:
  PYTHONPATH=ops/src \
  OPS_DB_CLUSTER_ARN=... \
  OPS_DB_SECRET_ARN=... \
  OPS_DB_NAME=timer_entry_ops \
  OANDA_SECRET_NAME=oanda_rest_api_key \
  DECISION_LOG_TABLE_NAME=timer-entry-runtime-decision-log \
  EXECUTION_LOG_TABLE_NAME=timer-entry-runtime-execution-log \
  python3 ops/scripts/backfill_exit_fields.py

Docker example:
  docker run --rm \
    --entrypoint /bin/bash \
    -v "$PWD:/work" \
    -v "$HOME/.aws:/root/.aws:ro" \
    -w /work \
    -e AWS_PROFILE \
    -e AWS_REGION=ap-northeast-1 \
    -e OPS_DB_CLUSTER_ARN='...' \
    -e OPS_DB_SECRET_ARN='...' \
    -e OPS_DB_NAME=timer_entry_ops \
    -e OANDA_SECRET_NAME=oanda_rest_api_key \
    -e DECISION_LOG_TABLE_NAME=timer-entry-runtime-decision-log \
    -e EXECUTION_LOG_TABLE_NAME=timer-entry-runtime-execution-log \
    python:3.12-slim \
    -lc "pip install boto3 && PYTHONPATH=ops/src python3 ops/scripts/backfill_exit_fields.py"
"""

import argparse

from timer_entry_ops.config import OpsConfig
from timer_entry_ops.data_api import DataApi


def _record_value(record: list[dict[str, object]], index: int) -> str:
    value = record[index]
    if not isinstance(value, dict):
        return ""
    if "stringValue" in value:
        return str(value["stringValue"])
    if "longValue" in value:
        return str(value["longValue"])
    if "doubleValue" in value:
        return str(value["doubleValue"])
    if value.get("isNull"):
        return ""
    return ""


def _close_reason_sql(schema: str) -> str:
    # Summarize how many rows can be resolved before updating anything.
    return f"""
with close_candidates as (
  select
    f.fact_event_id,
    n.transaction_id,
    n.transaction_time,
    n.reason as close_reason,
    row_number() over (
      partition by f.fact_event_id
      order by n.transaction_time desc, n.transaction_id desc
    ) as row_num
  from {schema}.runtime_oanda_event_fact f
  join {schema}.oanda_transactions_normalized n
    on n.trade_id = f.oanda_trade_id
  where f.decision = 'exited'
    and n.transaction_type = 'ORDER_FILL'
    and n.reason in (
      'TAKE_PROFIT_ORDER',
      'STOP_LOSS_ORDER',
      'MARKET_ORDER_TRADE_CLOSE',
      'TRAILING_STOP_LOSS_ORDER'
    )
),
resolved as (
  select
    f.fact_event_id,
    c.transaction_id as resolved_exit_transaction_id,
    case
      when c.close_reason = 'TAKE_PROFIT_ORDER' then 'tp_hit'
      when c.close_reason = 'STOP_LOSS_ORDER' then 'sl_hit'
      when c.close_reason = 'MARKET_ORDER_TRADE_CLOSE' then 'forced_exit'
      when c.close_reason = 'TRAILING_STOP_LOSS_ORDER' then 'broker_closed_other'
      when f.reason = 'forced_exit' then 'forced_exit'
      when f.reason = 'broker_closed' then 'broker_closed_other'
      else 'unknown'
    end as resolved_exit_reason
  from {schema}.runtime_oanda_event_fact f
  left join close_candidates c
    on c.fact_event_id = f.fact_event_id
   and c.row_num = 1
  where f.decision = 'exited'
)
select
  count(*) as exited_rows,
  count(*) filter (
    where resolved_exit_transaction_id is not null
  ) as matched_close_fill_rows,
  count(*) filter (
    where resolved_exit_transaction_id is null
  ) as unmatched_close_fill_rows,
  count(*) filter (
    where resolved_exit_transaction_id is not null
      and resolved_exit_transaction_id is distinct from current_exit_transaction_id
  ) as exit_transaction_id_updates,
  count(*) filter (
    where resolved_exit_reason is distinct from current_exit_reason
  ) as exit_reason_updates
from (
  select
    f.fact_event_id,
    f.exit_transaction_id as current_exit_transaction_id,
    f.exit_reason as current_exit_reason,
    r.resolved_exit_transaction_id,
    r.resolved_exit_reason
  from {schema}.runtime_oanda_event_fact f
  join resolved r
    on r.fact_event_id = f.fact_event_id
) summary
"""


def _sample_sql(schema: str) -> str:
    # Show a small sample so we can sanity-check the resolution logic in dry-run.
    return f"""
with close_candidates as (
  select
    f.fact_event_id,
    n.transaction_id,
    n.transaction_time,
    n.reason as close_reason,
    row_number() over (
      partition by f.fact_event_id
      order by n.transaction_time desc, n.transaction_id desc
    ) as row_num
  from {schema}.runtime_oanda_event_fact f
  join {schema}.oanda_transactions_normalized n
    on n.trade_id = f.oanda_trade_id
  where f.decision = 'exited'
    and n.transaction_type = 'ORDER_FILL'
    and n.reason in (
      'TAKE_PROFIT_ORDER',
      'STOP_LOSS_ORDER',
      'MARKET_ORDER_TRADE_CLOSE',
      'TRAILING_STOP_LOSS_ORDER'
    )
)
select
  f.fact_event_id,
  f.setting_id,
  f.reason as fact_reason,
  f.exit_transaction_id as current_exit_transaction_id,
  c.transaction_id as resolved_exit_transaction_id,
  f.exit_reason as current_exit_reason,
  case
    when c.close_reason = 'TAKE_PROFIT_ORDER' then 'tp_hit'
    when c.close_reason = 'STOP_LOSS_ORDER' then 'sl_hit'
    when c.close_reason = 'MARKET_ORDER_TRADE_CLOSE' then 'forced_exit'
    when c.close_reason = 'TRAILING_STOP_LOSS_ORDER' then 'broker_closed_other'
    when f.reason = 'forced_exit' then 'forced_exit'
    when f.reason = 'broker_closed' then 'broker_closed_other'
    else 'unknown'
  end as resolved_exit_reason
from {schema}.runtime_oanda_event_fact f
left join close_candidates c
  on c.fact_event_id = f.fact_event_id
 and c.row_num = 1
where f.decision = 'exited'
order by f.created_at desc
limit 20
"""


def _update_sql(schema: str) -> str:
    # Apply both corrections in one pass:
    # 1. fix exit_transaction_id to the true close-side ORDER_FILL transaction
    # 2. populate exit_reason from that close-side transaction reason
    return f"""
with close_candidates as (
  select
    f.fact_event_id,
    n.transaction_id,
    n.reason as close_reason,
    row_number() over (
      partition by f.fact_event_id
      order by n.transaction_time desc, n.transaction_id desc
    ) as row_num
  from {schema}.runtime_oanda_event_fact f
  join {schema}.oanda_transactions_normalized n
    on n.trade_id = f.oanda_trade_id
  where f.decision = 'exited'
    and n.transaction_type = 'ORDER_FILL'
    and n.reason in (
      'TAKE_PROFIT_ORDER',
      'STOP_LOSS_ORDER',
      'MARKET_ORDER_TRADE_CLOSE',
      'TRAILING_STOP_LOSS_ORDER'
    )
),
resolved as (
  select
    f.fact_event_id,
    c.transaction_id as resolved_exit_transaction_id,
    case
      when c.close_reason = 'TAKE_PROFIT_ORDER' then 'tp_hit'
      when c.close_reason = 'STOP_LOSS_ORDER' then 'sl_hit'
      when c.close_reason = 'MARKET_ORDER_TRADE_CLOSE' then 'forced_exit'
      when c.close_reason = 'TRAILING_STOP_LOSS_ORDER' then 'broker_closed_other'
      when f.reason = 'forced_exit' then 'forced_exit'
      when f.reason = 'broker_closed' then 'broker_closed_other'
      else 'unknown'
    end as resolved_exit_reason
  from {schema}.runtime_oanda_event_fact f
  left join close_candidates c
    on c.fact_event_id = f.fact_event_id
   and c.row_num = 1
  where f.decision = 'exited'
)
update {schema}.runtime_oanda_event_fact as fact
set
  exit_transaction_id = coalesce(resolved.resolved_exit_transaction_id, fact.exit_transaction_id),
  exit_reason = coalesce(resolved.resolved_exit_reason, fact.exit_reason),
  synced_at = now()
from resolved
where fact.fact_event_id = resolved.fact_event_id
"""


def _print_summary(data_api: DataApi, schema: str) -> None:
    response = data_api.execute(_close_reason_sql(schema))
    records = response.get("records", [])
    if not records:
        print("no summary rows returned")
        return
    row = records[0]
    print(f"schema={schema}")
    print(f"  exited_rows={_record_value(row, 0)}")
    print(f"  matched_close_fill_rows={_record_value(row, 1)}")
    print(f"  unmatched_close_fill_rows={_record_value(row, 2)}")
    print(f"  exit_transaction_id_updates={_record_value(row, 3)}")
    print(f"  exit_reason_updates={_record_value(row, 4)}")


def _print_sample(data_api: DataApi, schema: str) -> None:
    response = data_api.execute(_sample_sql(schema))
    records = response.get("records", [])
    if not records:
        print("no sample rows returned")
        return
    print("sample:")
    for record in records:
        print(
            "  "
            + ", ".join(
                [
                    f"fact_event_id={_record_value(record, 0)}",
                    f"setting_id={_record_value(record, 1)}",
                    f"fact_reason={_record_value(record, 2)}",
                    f"current_exit_transaction_id={_record_value(record, 3)}",
                    f"resolved_exit_transaction_id={_record_value(record, 4)}",
                    f"current_exit_reason={_record_value(record, 5)}",
                    f"resolved_exit_reason={_record_value(record, 6)}",
                ]
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    import boto3

    config = OpsConfig.from_env()
    schema = args.schema or config.main_schema
    session = boto3.session.Session(region_name=config.aws_region)
    data_api = DataApi(
        client=session.client("rds-data"),
        cluster_arn=config.database_cluster_arn,
        secret_arn=config.database_secret_arn,
        database_name=config.database_name,
    )

    # The script is intentionally safe by default. We always show the preview first.
    print("before:")
    _print_summary(data_api, schema)
    _print_sample(data_api, schema)

    if not args.apply:
        print("dry-run only. pass --apply to update rows.")
        return 0

    data_api.execute(_update_sql(schema))
    print("applied backfill")
    print("after:")
    _print_summary(data_api, schema)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
