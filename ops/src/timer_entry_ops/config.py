from __future__ import annotations

from dataclasses import dataclass
import os


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class OpsConfig:
    aws_region: str
    database_cluster_arn: str
    database_secret_arn: str
    database_name: str
    main_schema: str
    demo_schema: str
    oanda_secret_name: str
    decision_log_table_name: str
    execution_log_table_name: str
    log_scan_lookback_hours: int

    @classmethod
    def from_env(cls) -> "OpsConfig":
        return cls(
            aws_region=os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "ap-northeast-1")),
            database_cluster_arn=_require_env("OPS_DB_CLUSTER_ARN"),
            database_secret_arn=_require_env("OPS_DB_SECRET_ARN"),
            database_name=os.getenv("OPS_DB_NAME", "timer_entry_ops"),
            main_schema=os.getenv("OPS_MAIN_SCHEMA", "ops_main"),
            demo_schema=os.getenv("OPS_DEMO_SCHEMA", "ops_demo"),
            oanda_secret_name=_require_env("OANDA_SECRET_NAME"),
            decision_log_table_name=_require_env("DECISION_LOG_TABLE_NAME"),
            execution_log_table_name=_require_env("EXECUTION_LOG_TABLE_NAME"),
            log_scan_lookback_hours=int(os.getenv("LOG_SCAN_LOOKBACK_HOURS", "36")),
        )
