from __future__ import annotations

from dataclasses import dataclass
import os

from .constants import DEFAULT_SUPPORTED_MARKET_TIMEZONES


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class RuntimeConfig:
    app_name: str
    aws_region: str
    setting_config_table_name: str
    trade_state_table_name: str
    execution_log_table_name: str
    decision_log_table_name: str
    oanda_secret_name: str
    log_level: str
    mode: str
    supported_market_timezones: tuple[str, ...]
    trade_state_ttl_days: int
    decision_log_ttl_days: int
    forced_exit_retry_count: int
    build_version: str

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        supported_market_timezones = tuple(
            item.strip()
            for item in os.getenv(
                "SUPPORTED_MARKET_TIMEZONES",
                ",".join(DEFAULT_SUPPORTED_MARKET_TIMEZONES),
            ).split(",")
            if item.strip()
        )
        return cls(
            app_name=os.getenv("APP_NAME", "timer_entry_runtime"),
            aws_region=os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "ap-northeast-1")),
            setting_config_table_name=_require_env("SETTING_CONFIG_TABLE_NAME"),
            trade_state_table_name=_require_env("TRADE_STATE_TABLE_NAME"),
            execution_log_table_name=_require_env("EXECUTION_LOG_TABLE_NAME"),
            decision_log_table_name=_require_env("DECISION_LOG_TABLE_NAME"),
            oanda_secret_name=_require_env("OANDA_SECRET_NAME"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            mode=os.getenv("MODE", "runtime"),
            supported_market_timezones=supported_market_timezones,
            trade_state_ttl_days=int(os.getenv("TRADE_STATE_TTL_DAYS", "180")),
            decision_log_ttl_days=int(os.getenv("DECISION_LOG_TTL_DAYS", "365")),
            forced_exit_retry_count=int(os.getenv("FORCED_EXIT_RETRY_COUNT", "3")),
            build_version=os.getenv("BUILD_VERSION", "dev"),
        )

