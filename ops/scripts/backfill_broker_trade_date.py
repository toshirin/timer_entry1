from __future__ import annotations

"""
Backfill `runtime_oanda_event_fact.broker_trade_date`.

Purpose:
- Add a stable broker-day axis for ops-side aggregation.
- Preserve runtime's existing `trade_date_local` semantics while giving ops a
  New York 17:00 boundary based date for dashboard / anomaly / backtest usage.

Definition:
- `broker_trade_date` = the fact row occurrence date cut by the New York 17:00 boundary.
- Timestamp priority:
  - `exit_at` if `decision = 'exited'`
  - `entry_at` if `decision = 'entered'`
  - otherwise `created_at`

Default behavior is dry-run. It prints summary counts and sample rows only.
Actual updates happen only with `--apply`.

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
    -lc "pip install boto3 && PYTHONPATH=ops/src python3 ops/scripts/backfill_broker_trade_date.py"
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


def _resolved_broker_trade_date_expr() -> str:
    resolved_ts = """
coalesce(
  case when decision = 'exited' then exit_at end,
  case when decision = 'entered' then entry_at end,
  created_at
)
""".strip()
    local_ts = f"(({resolved_ts}) at time zone 'America/New_York')"
    return f"""
case
  when {resolved_ts} is null then null
  when ({local_ts})::time >= time '17:00:00' then (({local_ts})::date + 1)::text
  else ({local_ts})::date::text
end
""".strip()


def _summary_sql(schema: str) -> str:
    resolved_expr = _resolved_broker_trade_date_expr()
    return f"""
select
  count(*) as fact_rows,
  count(*) filter (where {resolved_expr} is not null) as resolvable_rows,
  count(*) filter (where {resolved_expr} is null) as unresolved_rows,
  count(*) filter (
    where {resolved_expr} is distinct from broker_trade_date
  ) as broker_trade_date_updates
from {schema}.runtime_oanda_event_fact
"""


def _sample_sql(schema: str) -> str:
    resolved_expr = _resolved_broker_trade_date_expr()
    return f"""
select
  fact_event_id,
  decision,
  trade_date_local,
  broker_trade_date,
  {resolved_expr} as resolved_broker_trade_date,
  entry_at::text,
  exit_at::text,
  created_at::text
from {schema}.runtime_oanda_event_fact
where {resolved_expr} is distinct from broker_trade_date
order by created_at desc
limit 20
"""


def _update_sql(schema: str) -> str:
    resolved_expr = _resolved_broker_trade_date_expr()
    return f"""
update {schema}.runtime_oanda_event_fact
set
  broker_trade_date = {resolved_expr},
  synced_at = now()
where {resolved_expr} is distinct from broker_trade_date
"""


def _print_summary(data_api: DataApi, schema: str) -> None:
    response = data_api.execute(_summary_sql(schema))
    records = response.get("records", [])
    if not records:
        print("no summary rows returned")
        return
    row = records[0]
    print(f"schema={schema}")
    print(f"  fact_rows={_record_value(row, 0)}")
    print(f"  resolvable_rows={_record_value(row, 1)}")
    print(f"  unresolved_rows={_record_value(row, 2)}")
    print(f"  broker_trade_date_updates={_record_value(row, 3)}")


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
                    f"decision={_record_value(record, 1)}",
                    f"trade_date_local={_record_value(record, 2)}",
                    f"broker_trade_date={_record_value(record, 3)}",
                    f"resolved_broker_trade_date={_record_value(record, 4)}",
                    f"entry_at={_record_value(record, 5)}",
                    f"exit_at={_record_value(record, 6)}",
                    f"created_at={_record_value(record, 7)}",
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
