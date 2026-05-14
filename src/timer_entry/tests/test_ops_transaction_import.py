from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "ops" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "runtime" / "src"))

from timer_entry_ops.daily_transaction_import import _normalized_transaction_values, _process_kill_switch_demotions


def test_normalized_transaction_values_extracts_account_balance_and_trade_ids() -> None:
    transaction = {
        "id": "1001",
        "accountID": "acct-1",
        "time": "2026-04-14T12:00:01.000000000Z",
        "type": "ORDER_FILL",
        "orderID": "order-1",
        "batchID": "batch-1",
        "instrument": "USD_JPY",
        "units": "-1000",
        "price": "151.234",
        "pl": "120.5",
        "financing": "-1.2",
        "accountBalance": "100119.3",
        "reason": "MARKET_ORDER",
        "tradesClosed": [{"tradeID": "trade-1"}],
        "clientOrderID": "setting-1",
        "clientOrderTag": "timed_entry_sell",
        "clientOrderComment": "tyo09:test",
    }

    values = _normalized_transaction_values(transaction)

    assert values["account_id"] == "acct-1"
    assert values["account_balance"] == "100119.3"
    assert values["trade_id"] == "trade-1"
    assert values["client_ext_id"] == "setting-1"
    assert values["pl"] == "120.5"


class FakeDataApi:
    def __init__(self, *, existing_pending_log: bool = False) -> None:
        self.existing_pending_log = existing_pending_log
        self.inserted_logs: list[list[dict[str, Any]]] = []
        self.applied_logs: list[list[dict[str, Any]]] = []

    def execute(self, sql: str, parameters: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if "from ops_main.runtime_oanda_event_fact f" in sql:
            pending_log = [
                {"stringValue": "kill_switch#fact-1"},
                {"booleanValue": False},
                {"longValue": 3},
                {"longValue": 2},
                {"stringValue": "demote"},
                {"stringValue": "kill_switch_triggered"},
                {"isNull": True},
                {"isNull": True},
                {"isNull": True},
                {"isNull": True},
                {"stringValue": "unit_level_policy"},
                {"stringValue": "2026-04-17"},
            ]
            empty_log = [{"isNull": True} for _ in range(12)]
            return {
                "records": [
                    [
                        {"stringValue": "fact-1"},
                        {"stringValue": "setting-1"},
                        {"stringValue": "2026-04-20"},
                        {"stringValue": "2026-04-20T22:00:00+00:00"},
                        *(pending_log if self.existing_pending_log else empty_log),
                    ]
                ]
            }
        if "insert into ops_main.unit_level_decision_log" in sql:
            self.inserted_logs.append(parameters or [])
            return {"numberOfRecordsUpdated": 1}
        if "update ops_main.unit_level_decision_log" in sql:
            self.applied_logs.append(parameters or [])
            return {"numberOfRecordsUpdated": 1}
        raise AssertionError(f"unexpected SQL: {sql}")


class FakeSettingTable:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    def get_item(self, Key: dict[str, str]) -> dict[str, Any]:
        assert Key == {"setting_id": "setting-1"}
        return {
            "Item": {
                "setting_id": "setting-1",
                "enabled": True,
                "strategy_id": "timed_entry_buy",
                "slot_id": "lon10",
                "market_session": "london",
                "market_tz": "Europe/London",
                "instrument": "USD_JPY",
                "side": "buy",
                "entry_clock_local": "10:00",
                "forced_exit_clock_local": "10:30",
                "trigger_bucket_entry": "ENTRY#Europe/London#1000",
                "trigger_bucket_exit": "EXIT#Europe/London#1030",
                "fixed_units": None,
                "margin_ratio_target": 150.0,
                "size_scale_pct": 1.0,
                "unit_level": 3,
                "unit_level_policy_name": "unit_level_policy",
                "unit_level_policy_version": "2026-04-17",
                "tp_pips": 15.0,
                "sl_pips": 30.0,
                "research_label": None,
                "labels": [],
                "market_open_check_seconds": 10,
                "max_concurrent_positions": 1,
                "kill_switch_dd_pct": -0.2,
                "kill_switch_reference_balance_jpy": 100000.0,
                "min_maintenance_margin_pct": 150.0,
                "filter_spec_json": None,
                "execution_spec_json": None,
                "notes": None,
            }
        }

    def update_item(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)


def _param(parameters: list[dict[str, Any]], name: str) -> str:
    for item in parameters:
        if item["name"] == name:
            return str(item["value"]["stringValue"])
    raise AssertionError(f"missing parameter: {name}")


def test_kill_switch_demotions_apply_one_level_and_log_event_id() -> None:
    data_api = FakeDataApi()
    setting_table = FakeSettingTable()

    results = _process_kill_switch_demotions(
        data_api=data_api,  # type: ignore[arg-type]
        schema="ops_main",
        setting_table=setting_table,
        now_utc=datetime(2026, 4, 21, 0, 0, tzinfo=timezone.utc),
    )

    assert results[0]["current_level"] == 3
    assert results[0]["next_level"] == 2
    assert results[0]["decision"] == "demote"
    assert results[0]["applied"] is True
    assert len(setting_table.updates) == 1
    values = setting_table.updates[0]["ExpressionAttributeValues"]
    assert values[":unit_level"] == 2
    assert values[":size_scale_pct"] == Decimal("0.3")
    assert values[":updated_by"] == "ops_kill_switch_unit_level_policy"
    assert len(data_api.inserted_logs) == 1
    assert _param(data_api.inserted_logs[0], "decision_log_id") == "kill_switch#fact-1"
    assert _param(data_api.inserted_logs[0], "source") == "kill_switch"
    assert _param(data_api.inserted_logs[0], "decision_month") == "2026-04"
    assert len(data_api.applied_logs) == 1


def test_kill_switch_demotions_resume_pending_log_without_second_demotion() -> None:
    data_api = FakeDataApi(existing_pending_log=True)
    setting_table = FakeSettingTable()

    results = _process_kill_switch_demotions(
        data_api=data_api,  # type: ignore[arg-type]
        schema="ops_main",
        setting_table=setting_table,
        now_utc=datetime(2026, 4, 21, 0, 0, tzinfo=timezone.utc),
    )

    assert results[0]["current_level"] == 3
    assert results[0]["next_level"] == 2
    assert results[0]["applied"] is True
    assert len(setting_table.updates) == 1
    values = setting_table.updates[0]["ExpressionAttributeValues"]
    assert values[":unit_level"] == 2
    assert data_api.inserted_logs == []
    assert len(data_api.applied_logs) == 1
