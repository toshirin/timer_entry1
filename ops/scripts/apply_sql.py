from __future__ import annotations

import argparse
from pathlib import Path

from timer_entry_ops.config import OpsConfig
from timer_entry_ops.data_api import DataApi


def split_sql(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    previous = ""
    for char in sql:
        if char == "'" and previous != "\\":
            in_single_quote = not in_single_quote
        if char == ";" and not in_single_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)
        previous = char
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sql_file", type=Path, nargs="?")
    parser.add_argument("--statement")
    args = parser.parse_args()
    if args.sql_file is None and not args.statement:
        parser.error("sql_file or --statement is required")

    import boto3

    config = OpsConfig.from_env()
    session = boto3.session.Session(region_name=config.aws_region)
    data_api = DataApi(
        client=session.client("rds-data"),
        cluster_arn=config.database_cluster_arn,
        secret_arn=config.database_secret_arn,
        database_name=config.database_name,
    )
    if args.statement:
        data_api.batch_execute(split_sql(args.statement))
        print("applied inline statement")
    if args.sql_file:
        data_api.batch_execute(split_sql(args.sql_file.read_text()))
        print(f"applied {args.sql_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
