from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "ops" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "runtime" / "src"))

from timer_entry_ops.monthly_unit_level_policy import process_setting
from timer_entry_runtime.models import AccountSnapshot, SettingConfig


class FakeDataApi:
    def __init__(self, *, existing_log: bool = False, existing_applied: bool = False, pnl: float = 0.0) -> None:
        self.existing_log = existing_log
        self.existing_applied = existing_applied
        self.pnl = pnl
        self.inserted_logs: list[list[dict[str, Any]]] = []
        self.applied_logs: list[list[dict[str, Any]]] = []

    def execute(self, sql: str, parameters: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if "from ops_main.unit_level_decision_log" in sql and "where decision_log_id" in sql:
            if not self.existing_log:
                return {"records": []}
            return {
                "records": [
                    [
                        {"stringValue": "monthly#2026-03#setting-1"},
                        {"booleanValue": self.existing_applied},
                        {"longValue": 0},
                        {"longValue": 1},
                        {"stringValue": "promote"},
                        {"stringValue": "monthly_profit_above_threshold"},
                        {"longValue": 10},
                        {"stringValue": "1.0"},
                        {"stringValue": "2.0"},
                        {"stringValue": "month_end_latest_equity_runtime_compute_units"},
                        {"stringValue": "unit_level_policy"},
                        {"stringValue": "2026-04-17"},
                    ]
                ]
            }
        if "coalesce(sum(pnl_jpy)" in sql:
            return {"records": [[{"stringValue": str(self.pnl)}, {"longValue": 1}]]}
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

    def update_item(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)


class FakeOandaClient:
    pass


def _setting(**overrides: Any) -> SettingConfig:
    values = {
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
        "fixed_units": 10,
        "margin_ratio_target": None,
        "size_scale_pct": None,
        "tp_pips": 15.0,
        "sl_pips": 30.0,
        "research_label": None,
        "labels": ["fix10"],
        "market_open_check_seconds": 10,
        "max_concurrent_positions": 1,
        "kill_switch_dd_pct": -0.2,
        "kill_switch_reference_balance_jpy": 100000.0,
        "min_maintenance_margin_pct": 150.0,
        "filter_spec_json": None,
        "execution_spec_json": None,
        "notes": None,
    }
    values.update(overrides)
    return SettingConfig(**values)


def _param(parameters: list[dict[str, Any]], name: str) -> str:
    for item in parameters:
        if item["name"] == name:
            return str(item["value"]["stringValue"])
    raise AssertionError(f"missing parameter: {name}")


def test_process_setting_promotes_level_zero_and_logs_decision() -> None:
    data_api = FakeDataApi(pnl=2.0)
    setting_table = FakeSettingTable()

    result = process_setting(
        data_api=data_api,  # type: ignore[arg-type]
        schema="ops_main",
        setting_table=setting_table,
        setting=_setting(),
        decision_month="2026-03",
        account=AccountSnapshot(account_id="acct-1", balance=1_000_000.0),
        oanda_client=FakeOandaClient(),  # type: ignore[arg-type]
        price_cache={},
        now_utc=datetime(2026, 4, 1, 0, 30, tzinfo=timezone.utc),
    )

    assert result["decision"] == "promote"
    assert result["current_level"] == 0
    assert result["next_level"] == 1
    assert result["applied"] is True
    assert len(setting_table.updates) == 1
    values = setting_table.updates[0]["ExpressionAttributeValues"]
    assert values[":unit_level"] == 1
    assert values[":fixed_units"] is None
    assert values[":size_scale_pct"] == Decimal("0.1")
    assert len(data_api.inserted_logs) == 1
    assert _param(data_api.inserted_logs[0], "decision_reason") == "monthly_profit_above_threshold"
    assert _param(data_api.inserted_logs[0], "threshold_jpy") == "1.0"
    assert len(data_api.applied_logs) == 1


def test_process_setting_skips_duplicate_applied_month() -> None:
    data_api = FakeDataApi(existing_log=True, existing_applied=True, pnl=2.0)
    setting_table = FakeSettingTable()

    result = process_setting(
        data_api=data_api,  # type: ignore[arg-type]
        schema="ops_main",
        setting_table=setting_table,
        setting=_setting(),
        decision_month="2026-03",
        account=AccountSnapshot(account_id="acct-1", balance=1_000_000.0),
        oanda_client=FakeOandaClient(),  # type: ignore[arg-type]
        price_cache={},
        now_utc=datetime(2026, 4, 1, 0, 30, tzinfo=timezone.utc),
    )

    assert result["status"] == "duplicate_skipped"
    assert setting_table.updates == []
    assert data_api.inserted_logs == []
    assert data_api.applied_logs == []


def test_process_setting_resumes_pending_log_without_recomputing_next_level() -> None:
    data_api = FakeDataApi(existing_log=True, existing_applied=False, pnl=999.0)
    setting_table = FakeSettingTable()

    result = process_setting(
        data_api=data_api,  # type: ignore[arg-type]
        schema="ops_main",
        setting_table=setting_table,
        setting=_setting(
            unit_level=1,
            fixed_units=None,
            size_scale_pct=0.1,
            unit_level_policy_name="unit_level_policy",
            unit_level_policy_version="2026-04-17",
        ),
        decision_month="2026-03",
        account=AccountSnapshot(account_id="acct-1", balance=1_000_000.0),
        oanda_client=FakeOandaClient(),  # type: ignore[arg-type]
        price_cache={},
        now_utc=datetime(2026, 4, 1, 0, 30, tzinfo=timezone.utc),
    )

    assert result["status"] == "resumed_pending_log"
    assert result["current_level"] == 0
    assert result["next_level"] == 1
    assert result["applied"] is False
    assert setting_table.updates == []
    assert data_api.inserted_logs == []
    assert len(data_api.applied_logs) == 1
