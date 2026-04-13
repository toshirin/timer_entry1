from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import json
from typing import Any

from .config import RuntimeConfig
from .models import OandaSecret, SettingConfig
from .time_utils import ttl_epoch_seconds


class RuntimeAws:
    def __init__(self, config: RuntimeConfig) -> None:
        import boto3
        from boto3.dynamodb.conditions import Key

        session = boto3.session.Session(region_name=config.aws_region)
        self._config = config
        self._key = Key
        self._secrets_client = session.client("secretsmanager")
        dynamodb_resource = session.resource("dynamodb")
        self._setting_config_table = dynamodb_resource.Table(config.setting_config_table_name)
        self._trade_state_table = dynamodb_resource.Table(config.trade_state_table_name)
        self._execution_log_table = dynamodb_resource.Table(config.execution_log_table_name)
        self._decision_log_table = dynamodb_resource.Table(config.decision_log_table_name)

    def get_oanda_secret(self) -> OandaSecret:
        response = self._secrets_client.get_secret_value(SecretId=self._config.oanda_secret_name)
        if "SecretString" not in response:
            raise RuntimeError("Binary secret is not supported for Oanda credentials")
        payload = json.loads(response["SecretString"])
        return OandaSecret(
            access_token=str(payload["access_token"]),
            account_id=str(payload["account_id"]),
            environment=str(payload.get("environment", "live")),
        )

    def _ddb_compatible(self, value: Any) -> Any:
        if isinstance(value, float):
            return Decimal(str(value))
        if isinstance(value, list):
            return [self._ddb_compatible(item) for item in value]
        if isinstance(value, dict):
            return {key: self._ddb_compatible(item) for key, item in value.items()}
        return value

    def query_settings_for_entry_bucket(self, trigger_bucket: str) -> list[SettingConfig]:
        response = self._setting_config_table.query(
            IndexName="gsi_entry_trigger",
            KeyConditionExpression=self._key("trigger_bucket_entry").eq(trigger_bucket),
        )
        return [SettingConfig.from_item(item) for item in response.get("Items", [])]

    def query_settings_for_exit_bucket(self, trigger_bucket: str) -> list[SettingConfig]:
        response = self._setting_config_table.query(
            IndexName="gsi_exit_trigger",
            KeyConditionExpression=self._key("trigger_bucket_exit").eq(trigger_bucket),
        )
        return [SettingConfig.from_item(item) for item in response.get("Items", [])]

    def create_trade_state_if_absent(self, item: dict[str, Any]) -> bool:
        try:
            self._trade_state_table.put_item(
                Item=self._ddb_compatible(item),
                ConditionExpression="attribute_not_exists(trade_id)",
            )
            return True
        except self._trade_state_table.meta.client.exceptions.ConditionalCheckFailedException:
            return False

    def update_trade_state(self, trade_id: str, **attributes: Any) -> None:
        self._update_item(self._trade_state_table, {"trade_id": trade_id}, attributes)

    def create_execution_log(self, item: dict[str, Any]) -> None:
        self._execution_log_table.put_item(Item=self._ddb_compatible(item))

    def update_execution_log(self, execution_id: str, **attributes: Any) -> None:
        self._update_item(self._execution_log_table, {"execution_id": execution_id}, attributes)

    def create_decision_log(self, item: dict[str, Any]) -> None:
        self._decision_log_table.put_item(Item=self._ddb_compatible(item))

    def _update_item(self, table: Any, key: dict[str, str], attributes: dict[str, Any]) -> None:
        update_parts: list[str] = []
        expression_values: dict[str, Any] = {}
        expression_names: dict[str, str] = {}
        for index, (name, value) in enumerate(attributes.items(), start=1):
            name_key = f"#n{index}"
            value_key = f":v{index}"
            expression_names[name_key] = name
            expression_values[value_key] = self._ddb_compatible(value)
            update_parts.append(f"{name_key} = {value_key}")
        if not update_parts:
            return
        table.update_item(
            Key=key,
            UpdateExpression="SET " + ", ".join(update_parts),
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values,
        )

    def query_entered_trade_states(self, setting_id: str) -> list[dict[str, Any]]:
        response = self._trade_state_table.query(
            IndexName="gsi_setting_status",
            KeyConditionExpression=self._key("setting_id").eq(setting_id) & self._key("status").eq("entered"),
        )
        return response.get("Items", [])

    def query_trade_states_for_setting(self, setting_id: str) -> list[dict[str, Any]]:
        response = self._trade_state_table.query(
            IndexName="gsi_setting_created_at",
            KeyConditionExpression=self._key("setting_id").eq(setting_id),
        )
        return response.get("Items", [])

    def build_trade_state_seed(
        self,
        *,
        trade_id: str,
        setting: SettingConfig,
        now_utc: datetime,
        trade_date_local: str,
        scheduled_entry_at_utc: str | None = None,
        scheduled_exit_at_utc: str | None = None,
    ) -> dict[str, Any]:
        return {
            "trade_id": trade_id,
            "idempotency_key": f"{setting.setting_id}#{trade_date_local}",
            "setting_id": setting.setting_id,
            "strategy_id": setting.strategy_id,
            "slot_id": setting.slot_id,
            "trade_date_local": trade_date_local,
            "market_tz": setting.market_tz,
            "instrument": setting.instrument,
            "side": setting.side,
            "status": "planned",
            "scheduled_entry_at_utc": scheduled_entry_at_utc,
            "scheduled_exit_at_utc": scheduled_exit_at_utc,
            "created_at": now_utc.isoformat(),
            "updated_at": now_utc.isoformat(),
            "ttl": ttl_epoch_seconds(now_utc, self._config.trade_state_ttl_days),
        }

    def build_execution_log_seed(
        self,
        *,
        execution_id: str,
        correlation_id: str,
        trade_id: str,
        setting: SettingConfig,
        units: int | None,
        requested_entry_time_local: str,
        requested_entry_time_utc: str,
        oanda_client_id: str,
        now_utc: datetime,
        trade_date_local: str,
    ) -> dict[str, Any]:
        return {
            "execution_id": execution_id,
            "correlation_id": correlation_id,
            "trade_id": trade_id,
            "setting_id": setting.setting_id,
            "strategy_id": setting.strategy_id,
            "slot_id": setting.slot_id,
            "trade_date_local": trade_date_local,
            "market_tz": setting.market_tz,
            "instrument": setting.instrument,
            "side": setting.side,
            "units": units,
            "requested_entry_time_local": requested_entry_time_local,
            "requested_entry_time_utc": requested_entry_time_utc,
            "oanda_order_id": None,
            "oanda_trade_id": None,
            "oanda_client_id": oanda_client_id,
            "status": "requested",
            "created_at": now_utc.isoformat(),
            "updated_at": now_utc.isoformat(),
        }

    def build_decision_log_seed(
        self,
        *,
        decision_id: str,
        correlation_id: str,
        setting: SettingConfig,
        handler_name: str,
        trigger_bucket: str | None,
        scheduled_local: str | None,
        actual_invoked_at_utc: str,
        trade_date_local: str,
        decision: str,
        reason: str | None,
        now_utc: datetime,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "decision_id": decision_id,
            "correlation_id": correlation_id,
            "setting_id": setting.setting_id,
            "strategy_id": setting.strategy_id,
            "slot_id": setting.slot_id,
            "trade_date_local": trade_date_local,
            "market_tz": setting.market_tz,
            "instrument": setting.instrument,
            "side": setting.side,
            "handler_name": handler_name,
            "trigger_bucket": trigger_bucket,
            "scheduled_local": scheduled_local,
            "actual_invoked_at_utc": actual_invoked_at_utc,
            "decision": decision,
            "reason": reason,
            "created_at": now_utc.isoformat(),
            "ttl": ttl_epoch_seconds(now_utc, self._config.decision_log_ttl_days),
            **(extra or {}),
        }
