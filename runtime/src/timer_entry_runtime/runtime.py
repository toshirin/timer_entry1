from __future__ import annotations

import traceback
from dataclasses import asdict
from datetime import datetime
from typing import Any

from timer_entry.calendar import is_trading_day_excluded
from timer_entry.direction import get_direction_spec

from .aws_runtime import RuntimeAws
from .config import RuntimeConfig
from .filtering import evaluate_filters
from .level_policy import WATCH_LABEL
from .logging_utils import emit_log
from .models import HandlerResult, SettingConfig, TriggerContext, pnl_pips
from .oanda_client import OandaApiError, OandaClient
from .order_builder import protection_levels, requested_entry_from_snapshot
from .sizing import compute_units
from .time_utils import (
    build_trigger_bucket,
    local_clock_matches,
    scheduled_clock_iso_for_date,
    scheduled_local_iso,
    trade_date_local,
    utc_now,
)


def build_trigger_context(handler_name: str, event: dict[str, Any]) -> TriggerContext:
    return TriggerContext(
        handler_name=handler_name,
        requested_trigger_bucket=event.get("trigger_bucket") if isinstance(event, dict) else None,
        invoked_at_utc=utc_now().isoformat(),
    )


def _trigger_buckets(event: dict[str, Any], prefix: str, now_utc: datetime, supported_timezones: tuple[str, ...]) -> list[str]:
    requested = event.get("trigger_bucket")
    if isinstance(requested, str) and requested:
        return [requested]
    if isinstance(requested, list):
        return [item for item in requested if isinstance(item, str) and item]
    return [build_trigger_bucket(prefix, tz_name, now_utc) for tz_name in supported_timezones]


def _query_settings(
    aws_runtime: RuntimeAws,
    *,
    handler_name: str,
    buckets: list[str],
    entry_mode: bool,
) -> list[SettingConfig]:
    settings: dict[str, SettingConfig] = {}
    for bucket in buckets:
        bucket_settings = (
            aws_runtime.query_settings_for_entry_bucket(bucket)
            if entry_mode
            else aws_runtime.query_settings_for_exit_bucket(bucket)
        )
        for setting in bucket_settings:
            settings[setting.setting_id] = setting
    emit_log(
        "SETTING_SCAN",
        handler_name=handler_name,
        trigger_buckets=buckets,
        setting_count=len(settings),
        setting_ids=sorted(settings.keys()),
    )
    return list(settings.values())


def _decision_id(setting: SettingConfig, handler_name: str, now_utc: datetime) -> str:
    return f"{setting.setting_id}#{trade_date_local(now_utc, setting.market_tz)}#{handler_name}#{int(now_utc.timestamp())}"


def _record_decision(
    *,
    aws_runtime: RuntimeAws,
    setting: SettingConfig,
    handler_name: str,
    trigger_bucket: str | None,
    scheduled_local: str | None,
    now_utc: datetime,
    decision: str,
    reason: str | None,
    correlation_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    try:
        decision_id = _decision_id(setting, handler_name, now_utc)
        effective_correlation_id = (
            correlation_id
            or (str(extra["trade_id"]) if extra and extra.get("trade_id") is not None else None)
            or decision_id
        )
        aws_runtime.create_decision_log(
            aws_runtime.build_decision_log_seed(
                decision_id=decision_id,
                correlation_id=effective_correlation_id,
                setting=setting,
                handler_name=handler_name,
                trigger_bucket=trigger_bucket,
                scheduled_local=scheduled_local,
                actual_invoked_at_utc=now_utc.isoformat(),
                trade_date_local=trade_date_local(now_utc, setting.market_tz),
                decision=decision,
                reason=reason,
                now_utc=now_utc,
                extra=extra,
            )
        )
    except Exception as exc:  # noqa: BLE001
        emit_log("DECISION_LOG_ERROR", setting_id=setting.setting_id, error=str(exc))


def _oanda_fill_time_iso(raw_response: dict[str, Any] | None, fallback: str) -> str:
    if not raw_response:
        return fallback
    fill = raw_response.get("orderFillTransaction")
    if isinstance(fill, dict) and fill.get("time"):
        return str(fill["time"])
    return fallback


def _market_open_check(
    *,
    setting: SettingConfig,
    oanda_client: OandaClient,
    now_utc: datetime,
) -> tuple[bool, Any]:
    price = oanda_client.get_price_snapshot(setting.instrument)
    market_open = OandaClient.is_market_open(price.time_utc, now_utc, setting.market_open_check_seconds)
    emit_log(
        "SETTING_CHECK",
        setting_id=setting.setting_id,
        check_name="market_open",
        market_open=market_open,
        threshold_seconds=setting.market_open_check_seconds,
        price_time_utc=price.time_utc.isoformat(),
        price_bid=price.bid,
        price_ask=price.ask,
    )
    return market_open, price


def _filter_checks(
    *,
    setting: SettingConfig,
    oanda_client: OandaClient,
    now_utc: datetime,
) -> tuple[bool, list[dict[str, Any]]]:
    filter_specs = setting.parsed_filter_specs()
    if not filter_specs:
        return True, []
    candles = oanda_client.get_recent_bid_candles(setting.instrument)
    decisions = evaluate_filters(setting=setting, now_utc=now_utc, candles=candles)
    serialized = [asdict(decision) for decision in decisions]
    emit_log("SETTING_FILTER", setting_id=setting.setting_id, filter_results=serialized)
    return all(item["passed"] for item in serialized), serialized


def _exclude_window_check(*, setting: SettingConfig, now_utc: datetime) -> tuple[bool, dict[str, Any]]:
    execution_spec = setting.parsed_execution_spec()
    raw_windows = execution_spec.get("exclude_windows", [])
    if raw_windows is None:
        raw_windows = []
    if isinstance(raw_windows, str):
        exclude_windows = [raw_windows]
    elif isinstance(raw_windows, list):
        exclude_windows = [str(item) for item in raw_windows]
    else:
        raise ValueError("execution_spec_json.exclude_windows must be a string or array")

    session_date = trade_date_local(now_utc, setting.market_tz)
    details: dict[str, Any] = {
        "exclude_windows": exclude_windows,
        "session_date": session_date,
        "session_tz": setting.market_tz,
    }
    if not exclude_windows:
        details["trigger_reason"] = None
        return True, details

    excluded = is_trading_day_excluded(session_date, setting.market_tz, exclude_windows)
    details["trigger_reason"] = "exclude_window" if excluded else None
    return not excluded, details


def _open_trade_setting_id(open_trade: dict[str, Any]) -> str | None:
    for key in ("clientExtensions", "tradeClientExtensions"):
        extensions = open_trade.get(key)
        if isinstance(extensions, dict) and extensions.get("id"):
            return str(extensions["id"])
    return None


def _has_watch_label(setting: SettingConfig | None) -> bool:
    if setting is None:
        return False
    return any(str(label).strip().lower() == WATCH_LABEL for label in setting.labels)


def _concurrency_check(
    *,
    setting: SettingConfig,
    oanda_client: OandaClient,
    aws_runtime: RuntimeAws,
) -> tuple[bool, dict[str, Any]]:
    max_concurrent_positions = setting.max_concurrent_positions
    open_trades = oanda_client.get_open_trades()
    blocking_trades: list[dict[str, Any]] = []
    ignored_watch_trades: list[dict[str, Any]] = []
    open_trade_setting_ids: list[str | None] = []
    setting_cache: dict[str, SettingConfig | None] = {}

    for trade in open_trades:
        trade_setting_id = _open_trade_setting_id(trade)
        open_trade_setting_ids.append(trade_setting_id)
        trade_setting = None
        if trade_setting_id:
            if trade_setting_id not in setting_cache:
                setting_cache[trade_setting_id] = aws_runtime.get_setting_config(trade_setting_id)
            trade_setting = setting_cache[trade_setting_id]
        if _has_watch_label(trade_setting):
            ignored_watch_trades.append(trade)
        else:
            blocking_trades.append(trade)

    details: dict[str, Any] = {
        "max_concurrent_positions": max_concurrent_positions,
        "open_trade_count": len(open_trades),
        "open_trade_ids": [str(item.get("id")) for item in open_trades if item.get("id") is not None],
        "open_trade_setting_ids": open_trade_setting_ids,
        "blocking_open_trade_count": len(blocking_trades),
        "blocking_open_trade_ids": [str(item.get("id")) for item in blocking_trades if item.get("id") is not None],
        "ignored_watch_open_trade_count": len(ignored_watch_trades),
        "ignored_watch_open_trade_ids": [
            str(item.get("id")) for item in ignored_watch_trades if item.get("id") is not None
        ],
    }
    if max_concurrent_positions is None:
        details["trigger_reason"] = None
        return True, details
    if len(blocking_trades) >= max_concurrent_positions:
        details["trigger_reason"] = "open_position_limit_reached"
        details["blocking_trade_id"] = (
            str(blocking_trades[0].get("id"))
            if blocking_trades and blocking_trades[0].get("id") is not None
            else None
        )
        details["blocking_trade_setting_id"] = (
            _open_trade_setting_id(blocking_trades[0]) if blocking_trades else None
        )
        return False, details
    details["trigger_reason"] = None
    return True, details


def _kill_switch_check(
    *,
    aws_runtime: RuntimeAws,
    setting: SettingConfig,
    estimated_margin_ratio_after_entry: float | None,
) -> tuple[bool, dict[str, Any]]:
    details: dict[str, Any] = {
        "kill_switch_dd_pct": setting.kill_switch_dd_pct,
        "kill_switch_reference_balance_jpy": setting.kill_switch_reference_balance_jpy,
        "min_maintenance_margin_pct": setting.min_maintenance_margin_pct,
        "estimated_margin_ratio_after_entry": estimated_margin_ratio_after_entry,
    }
    if (
        setting.min_maintenance_margin_pct is not None
        and estimated_margin_ratio_after_entry is not None
        and estimated_margin_ratio_after_entry < setting.min_maintenance_margin_pct
    ):
        details["trigger_reason"] = "maintenance_margin_below_threshold"
        return False, details

    if setting.kill_switch_dd_pct is None or setting.kill_switch_reference_balance_jpy is None:
        details["trigger_reason"] = None
        return True, details

    trade_states = aws_runtime.query_trade_states_for_setting(setting.setting_id)
    realized = [
        float(item["pnl_jpy"])
        for item in trade_states
        if item.get("status") == "exited" and item.get("pnl_jpy") is not None
    ]
    equity = float(setting.kill_switch_reference_balance_jpy)
    peak = equity
    max_drawdown_pct = 0.0
    for pnl_jpy_value in realized:
        equity += pnl_jpy_value
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown_pct = min(max_drawdown_pct, equity / peak - 1.0)
    details["realized_trade_count"] = len(realized)
    details["max_drawdown_pct"] = max_drawdown_pct
    if max_drawdown_pct <= setting.kill_switch_dd_pct:
        details["trigger_reason"] = "drawdown_threshold_breached"
        return False, details
    details["trigger_reason"] = None
    return True, details


def _create_entry_trade(
    *,
    aws_runtime: RuntimeAws,
    config: RuntimeConfig,
    oanda_client: OandaClient,
    setting: SettingConfig,
    now_utc: datetime,
    price_snapshot: Any,
) -> dict[str, Any]:
    trade_id = f"{setting.setting_id}#{trade_date_local(now_utc, setting.market_tz)}"
    correlation_id = trade_id
    execution_id = f"{trade_id}#{int(now_utc.timestamp())}"
    scheduled_local = scheduled_clock_iso_for_date(now_utc, setting.market_tz, setting.entry_clock_local)
    seed = aws_runtime.build_trade_state_seed(
        trade_id=trade_id,
        setting=setting,
        now_utc=now_utc,
        trade_date_local=trade_date_local(now_utc, setting.market_tz),
        scheduled_entry_at_utc=now_utc.isoformat(),
    )
    if not aws_runtime.create_trade_state_if_absent(seed):
        emit_log("SETTING_SKIP", setting_id=setting.setting_id, reason="duplicate_trade_state", trade_id=trade_id)
        _record_decision(
            aws_runtime=aws_runtime,
            setting=setting,
            handler_name="entry_handler",
            trigger_bucket=setting.trigger_bucket_entry,
            scheduled_local=scheduled_local,
            now_utc=now_utc,
            decision="skipped_duplicate",
            reason="duplicate_trade_state",
            extra={"trade_id": trade_id},
        )
        return {"setting_id": setting.setting_id, "status": "skipped_duplicate", "trade_id": trade_id}

    market_order_created = False
    entry_recorded = False
    tp_sl_requested = False
    try:
        account = oanda_client.get_account_snapshot()
        sizing = compute_units(setting=setting, account=account, price=price_snapshot)
        requested_entry = requested_entry_from_snapshot(setting, price_snapshot)
        emit_log(
            "SETTING_CHECK",
            setting_id=setting.setting_id,
            check_name="sizing",
            requested_units=sizing.requested_units,
            sizing_basis=sizing.sizing_basis,
            effective_margin_ratio=sizing.effective_margin_ratio,
            estimated_margin_ratio_after_entry=sizing.estimated_margin_ratio_after_entry,
            balance=account.balance,
            margin_price=sizing.margin_price,
            margin_price_side=sizing.margin_price_side,
        )

        kill_switch_allowed, kill_switch_details = _kill_switch_check(
            aws_runtime=aws_runtime,
            setting=setting,
            estimated_margin_ratio_after_entry=sizing.estimated_margin_ratio_after_entry,
        )
        emit_log("SETTING_CHECK", setting_id=setting.setting_id, check_name="kill_switch", **kill_switch_details, passed=kill_switch_allowed)
        if not kill_switch_allowed:
            aws_runtime.update_trade_state(
                trade_id,
                status="skipped_kill_switch",
                requested_units=sizing.requested_units,
                sizing_basis=sizing.sizing_basis,
                estimated_margin_ratio_after_entry=sizing.estimated_margin_ratio_after_entry,
                updated_at=now_utc.isoformat(),
            )
            _record_decision(
                aws_runtime=aws_runtime,
                setting=setting,
                handler_name="entry_handler",
                trigger_bucket=setting.trigger_bucket_entry,
                scheduled_local=scheduled_local,
                now_utc=now_utc,
                decision="skipped_kill_switch",
                reason=kill_switch_details.get("trigger_reason"),
                extra={"trade_id": trade_id, **kill_switch_details},
            )
            return {"setting_id": setting.setting_id, "status": "skipped_kill_switch", "trade_id": trade_id}

        client_id = setting.setting_id
        client_comment = f"{setting.slot_id}:{config.build_version}"[:128]
        aws_runtime.create_execution_log(
            aws_runtime.build_execution_log_seed(
                execution_id=execution_id,
                correlation_id=correlation_id,
                trade_id=trade_id,
                setting=setting,
                units=sizing.requested_units,
                requested_entry_time_local=scheduled_local,
                requested_entry_time_utc=now_utc.isoformat(),
                oanda_client_id=client_id,
                now_utc=now_utc,
                trade_date_local=trade_date_local(now_utc, setting.market_tz),
            )
        )
        aws_runtime.update_execution_log(
            execution_id,
            requested_units=sizing.requested_units,
            sizing_basis=sizing.sizing_basis,
            balance=account.balance,
            effective_margin_ratio=sizing.effective_margin_ratio,
            estimated_margin_ratio_after_entry=sizing.estimated_margin_ratio_after_entry,
            margin_price=sizing.margin_price,
            margin_price_side=sizing.margin_price_side,
            requested_entry_price=requested_entry.price,
            requested_entry_price_side=requested_entry.price_side,
            updated_at=now_utc.isoformat(),
        )
        order_result = oanda_client.create_market_order(
            setting=setting,
            units=sizing.requested_units,
            client_id=client_id,
            client_tag=setting.strategy_id,
            client_comment=client_comment,
        )
        if order_result.fill_price is None or order_result.trade_id is None:
            raise RuntimeError("entry market order did not return fill_price or trade_id")
        market_order_created = True

        levels = protection_levels(setting, entry_fill_price=order_result.fill_price)
        aws_runtime.update_execution_log(
            execution_id,
            status="order_created",
            oanda_order_id=order_result.order_id,
            oanda_trade_id=order_result.trade_id,
            requested_entry_price=requested_entry.price,
            requested_entry_price_side=requested_entry.price_side,
            entry_price_side=requested_entry.price_side,
            updated_at=now_utc.isoformat(),
        )
        aws_runtime.update_trade_state(
            trade_id,
            status="entered",
            requested_units=sizing.requested_units,
            sizing_basis=sizing.sizing_basis,
            estimated_margin_ratio_after_entry=sizing.estimated_margin_ratio_after_entry,
            entry_order_id=order_result.order_id,
            entry_trade_id=order_result.trade_id,
            entry_filled_at=_oanda_fill_time_iso(order_result.raw_response, now_utc.isoformat()),
            requested_entry_price=requested_entry.price,
            requested_entry_price_side=requested_entry.price_side,
            entry_price=order_result.fill_price,
            entry_price_side=requested_entry.price_side,
            tp_trigger_price=levels.tp_trigger_price,
            tp_trigger_side=levels.tp_trigger_side,
            sl_trigger_price=levels.sl_trigger_price,
            sl_trigger_side=levels.sl_trigger_side,
            scheduled_entry_at_utc=now_utc.isoformat(),
            updated_at=now_utc.isoformat(),
        )
        entry_recorded = True

        aws_runtime.update_execution_log(
            execution_id,
            status="tp_sl_requested",
            updated_at=now_utc.isoformat(),
        )
        tp_sl_requested = True
        protection_result = oanda_client.set_trade_protection_orders(
            trade_id=order_result.trade_id,
            setting=setting,
            entry_fill_price=order_result.fill_price,
        )
        aws_runtime.update_execution_log(
            execution_id,
            status="tp_sl_created",
            tp_trigger_side=levels.tp_trigger_side,
            sl_trigger_side=levels.sl_trigger_side,
            updated_at=now_utc.isoformat(),
        )
        aws_runtime.update_trade_state(
            trade_id,
            status="entered",
            tp_trigger_side=levels.tp_trigger_side,
            sl_trigger_side=levels.sl_trigger_side,
            updated_at=now_utc.isoformat(),
        )
        emit_log(
            "SETTING_ENTER",
            setting_id=setting.setting_id,
            trade_id=trade_id,
            instrument=setting.instrument,
            side=setting.side,
            requested_units=sizing.requested_units,
            order_id=order_result.order_id,
            entry_trade_id=order_result.trade_id,
            fill_price=order_result.fill_price,
            requested_entry_price=requested_entry.price,
            requested_entry_price_side=requested_entry.price_side,
        )
        emit_log(
            "SETTING_TP_SL",
            setting_id=setting.setting_id,
            trade_id=trade_id,
            tp_trigger_price=levels.tp_trigger_price,
            tp_trigger_side=levels.tp_trigger_side,
            sl_trigger_price=levels.sl_trigger_price,
            sl_trigger_side=levels.sl_trigger_side,
            take_profit_order_id=protection_result.take_profit_order_id,
            stop_loss_order_id=protection_result.stop_loss_order_id,
        )
        _record_decision(
            aws_runtime=aws_runtime,
            setting=setting,
            handler_name="entry_handler",
            trigger_bucket=setting.trigger_bucket_entry,
            scheduled_local=scheduled_local,
            now_utc=now_utc,
            decision="entered",
            reason=None,
            correlation_id=correlation_id,
            extra={"trade_id": trade_id, "entry_trade_id": order_result.trade_id},
        )
        return {
            "setting_id": setting.setting_id,
            "status": "entered",
            "trade_id": trade_id,
            "entry_trade_id": order_result.trade_id,
            "requested_units": sizing.requested_units,
        }
    except Exception:
        if tp_sl_requested or entry_recorded:
            aws_runtime.update_execution_log(execution_id, status="tp_sl_failed", updated_at=now_utc.isoformat())
            decision = "tp_sl_failed"
            reason = "tp_sl_exception"
        elif market_order_created:
            aws_runtime.update_execution_log(execution_id, status="entry_state_failed", updated_at=now_utc.isoformat())
            aws_runtime.update_trade_state(trade_id, status="entry_state_failed", updated_at=now_utc.isoformat())
            decision = "entry_state_failed"
            reason = "state_update_exception"
        else:
            aws_runtime.update_execution_log(execution_id, status="order_failed", updated_at=now_utc.isoformat())
            aws_runtime.update_trade_state(trade_id, status="entry_failed", updated_at=now_utc.isoformat())
            decision = "entry_failed"
            reason = "order_exception"
        _record_decision(
            aws_runtime=aws_runtime,
            setting=setting,
            handler_name="entry_handler",
            trigger_bucket=setting.trigger_bucket_entry,
            scheduled_local=scheduled_local,
            now_utc=now_utc,
            decision=decision,
            reason=reason,
            correlation_id=correlation_id,
            extra={"trade_id": trade_id},
        )
        raise


def run_entry_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    config = RuntimeConfig.from_env()
    now_utc = utc_now()
    trigger = build_trigger_context(handler_name="entry_handler", event=event)
    aws_runtime = RuntimeAws(config)
    oanda_client = OandaClient(aws_runtime.get_oanda_secret())

    buckets = _trigger_buckets(event, "ENTRY", now_utc, config.supported_market_timezones)
    settings = _query_settings(aws_runtime, handler_name="entry_handler", buckets=buckets, entry_mode=True)

    results: list[dict[str, Any]] = []
    for setting in settings:
        scheduled_local = scheduled_clock_iso_for_date(now_utc, setting.market_tz, setting.entry_clock_local)
        try:
            clock_match = local_clock_matches(now_utc, setting.market_tz, setting.entry_clock_local)
            emit_log(
                "SETTING_CHECK",
                setting_id=setting.setting_id,
                check_name="base",
                enabled=setting.enabled,
                clock_match=clock_match,
                scheduled_local=scheduled_local,
                actual_local=scheduled_local_iso(now_utc, setting.market_tz),
                trigger_bucket_entry=setting.trigger_bucket_entry,
            )
            if not setting.enabled:
                emit_log("SETTING_SKIP", setting_id=setting.setting_id, reason="disabled")
                _record_decision(aws_runtime=aws_runtime, setting=setting, handler_name="entry_handler", trigger_bucket=setting.trigger_bucket_entry, scheduled_local=scheduled_local, now_utc=now_utc, decision="skipped_disabled", reason="disabled")
                results.append({"setting_id": setting.setting_id, "status": "skipped_disabled"})
                continue
            if not clock_match:
                emit_log("SETTING_SKIP", setting_id=setting.setting_id, reason="clock_mismatch")
                _record_decision(aws_runtime=aws_runtime, setting=setting, handler_name="entry_handler", trigger_bucket=setting.trigger_bucket_entry, scheduled_local=scheduled_local, now_utc=now_utc, decision="skipped_clock_mismatch", reason="clock_mismatch")
                results.append({"setting_id": setting.setting_id, "status": "skipped_clock_mismatch"})
                continue

            exclude_allowed, exclude_details = _exclude_window_check(setting=setting, now_utc=now_utc)
            emit_log("SETTING_CHECK", setting_id=setting.setting_id, check_name="exclude_window", **exclude_details, passed=exclude_allowed)
            if not exclude_allowed:
                emit_log("SETTING_SKIP", setting_id=setting.setting_id, reason="exclude_window", exclude_window_details=exclude_details)
                _record_decision(
                    aws_runtime=aws_runtime,
                    setting=setting,
                    handler_name="entry_handler",
                    trigger_bucket=setting.trigger_bucket_entry,
                    scheduled_local=scheduled_local,
                    now_utc=now_utc,
                    decision="skipped_exclude_window",
                    reason="exclude_window",
                    extra=exclude_details,
                )
                results.append({"setting_id": setting.setting_id, "status": "skipped_exclude_window"})
                continue

            market_open, price_snapshot = _market_open_check(setting=setting, oanda_client=oanda_client, now_utc=now_utc)
            if not market_open:
                emit_log("SETTING_SKIP", setting_id=setting.setting_id, reason="market_closed")
                _record_decision(aws_runtime=aws_runtime, setting=setting, handler_name="entry_handler", trigger_bucket=setting.trigger_bucket_entry, scheduled_local=scheduled_local, now_utc=now_utc, decision="skipped_market_closed", reason="market_closed")
                results.append({"setting_id": setting.setting_id, "status": "skipped_market_closed"})
                continue

            concurrency_allowed, concurrency_details = _concurrency_check(
                setting=setting,
                oanda_client=oanda_client,
                aws_runtime=aws_runtime,
            )
            emit_log("SETTING_CHECK", setting_id=setting.setting_id, check_name="concurrency", **concurrency_details, passed=concurrency_allowed)
            if not concurrency_allowed:
                emit_log("SETTING_SKIP", setting_id=setting.setting_id, reason="open_position_exists", concurrency_details=concurrency_details)
                _record_decision(aws_runtime=aws_runtime, setting=setting, handler_name="entry_handler", trigger_bucket=setting.trigger_bucket_entry, scheduled_local=scheduled_local, now_utc=now_utc, decision="skipped_concurrency", reason="open_position_exists", extra=concurrency_details)
                results.append({"setting_id": setting.setting_id, "status": "skipped_concurrency"})
                continue

            filter_passed, filter_details = _filter_checks(setting=setting, oanda_client=oanda_client, now_utc=now_utc)
            if not filter_passed:
                emit_log("SETTING_SKIP", setting_id=setting.setting_id, reason="filter_rejected", filter_details=filter_details)
                _record_decision(aws_runtime=aws_runtime, setting=setting, handler_name="entry_handler", trigger_bucket=setting.trigger_bucket_entry, scheduled_local=scheduled_local, now_utc=now_utc, decision="skipped_filter", reason="filter_rejected", extra={"filter_results": filter_details})
                results.append({"setting_id": setting.setting_id, "status": "skipped_filter"})
                continue

            results.append(
                _create_entry_trade(
                    aws_runtime=aws_runtime,
                    config=config,
                    oanda_client=oanda_client,
                    setting=setting,
                    now_utc=now_utc,
                    price_snapshot=price_snapshot,
                )
            )
        except Exception as exc:  # noqa: BLE001
            emit_log("SETTING_ERROR", setting_id=setting.setting_id, error=str(exc), traceback=traceback.format_exc())
            results.append({"setting_id": setting.setting_id, "status": "error", "error": str(exc)})

    return HandlerResult(status="ok", message="entry handler processed", details={"trigger": asdict(trigger), "result_count": len(results), "results": results}).to_dict()


def run_forced_exit_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    config = RuntimeConfig.from_env()
    now_utc = utc_now()
    trigger = build_trigger_context(handler_name="forced_exit_handler", event=event)
    aws_runtime = RuntimeAws(config)
    oanda_client = OandaClient(aws_runtime.get_oanda_secret())

    buckets = _trigger_buckets(event, "EXIT", now_utc, config.supported_market_timezones)
    settings = _query_settings(aws_runtime, handler_name="forced_exit_handler", buckets=buckets, entry_mode=False)

    results: list[dict[str, Any]] = []
    for setting in settings:
        trade_id_for_error: str | None = None
        scheduled_local = scheduled_clock_iso_for_date(now_utc, setting.market_tz, setting.forced_exit_clock_local)
        exit_side = get_direction_spec(setting.side).exit_price_side
        try:
            clock_match = local_clock_matches(now_utc, setting.market_tz, setting.forced_exit_clock_local)
            emit_log("SETTING_CHECK", setting_id=setting.setting_id, check_name="exit_base", enabled=setting.enabled, clock_match=clock_match, scheduled_local=scheduled_local, actual_local=scheduled_local_iso(now_utc, setting.market_tz), trigger_bucket_exit=setting.trigger_bucket_exit)
            if not clock_match:
                emit_log("SETTING_SKIP", setting_id=setting.setting_id, reason="clock_mismatch")
                _record_decision(aws_runtime=aws_runtime, setting=setting, handler_name="forced_exit_handler", trigger_bucket=setting.trigger_bucket_exit, scheduled_local=scheduled_local, now_utc=now_utc, decision="skipped_clock_mismatch", reason="clock_mismatch")
                results.append({"setting_id": setting.setting_id, "status": "skipped_clock_mismatch"})
                continue

            entered_states = aws_runtime.query_entered_trade_states(setting.setting_id)
            if not entered_states:
                emit_log("SETTING_SKIP", setting_id=setting.setting_id, reason="no_entered_state")
                _record_decision(aws_runtime=aws_runtime, setting=setting, handler_name="forced_exit_handler", trigger_bucket=setting.trigger_bucket_exit, scheduled_local=scheduled_local, now_utc=now_utc, decision="skipped_no_entered_state", reason="no_entered_state")
                results.append({"setting_id": setting.setting_id, "status": "skipped_no_entered_state"})
                continue

            market_open, _ = _market_open_check(setting=setting, oanda_client=oanda_client, now_utc=now_utc)
            if not market_open:
                emit_log("SETTING_SKIP", setting_id=setting.setting_id, reason="market_closed")
                _record_decision(aws_runtime=aws_runtime, setting=setting, handler_name="forced_exit_handler", trigger_bucket=setting.trigger_bucket_exit, scheduled_local=scheduled_local, now_utc=now_utc, decision="skipped_market_closed", reason="market_closed")
                results.append({"setting_id": setting.setting_id, "status": "skipped_market_closed"})
                continue

            state = entered_states[0]
            trade_id = str(state["trade_id"])
            trade_id_for_error = trade_id
            entry_trade_id = state.get("entry_trade_id")
            if not entry_trade_id:
                raise RuntimeError("entry_trade_id is missing for entered trade_state")

            trade_details = oanda_client.get_trade(str(entry_trade_id))
            trade_state = str(trade_details.get("state", ""))
            if trade_state and trade_state != "OPEN":
                realized_pl = float(trade_details["realizedPL"]) if trade_details.get("realizedPL") is not None else None
                average_close_price = float(trade_details["averageClosePrice"]) if trade_details.get("averageClosePrice") is not None else None
                aws_runtime.update_trade_state(
                    trade_id,
                    status="exited",
                    exit_filled_at=str(trade_details.get("closeTime", now_utc.isoformat())),
                    exit_price=average_close_price,
                    exit_price_side=exit_side,
                    exit_reason="broker_closed",
                    pnl_jpy=realized_pl,
                    pnl_pips=(pnl_pips(float(state["entry_price"]), average_close_price, setting.side) if state.get("entry_price") is not None and average_close_price is not None else None),
                    scheduled_exit_at_utc=now_utc.isoformat(),
                    updated_at=now_utc.isoformat(),
                )
                emit_log("SETTING_EXIT", setting_id=setting.setting_id, trade_id=trade_id, entry_trade_id=entry_trade_id, exit_price=average_close_price, exit_price_side=exit_side, exit_reason="broker_closed", pnl_jpy=realized_pl)
                _record_decision(
                    aws_runtime=aws_runtime,
                    setting=setting,
                    handler_name="forced_exit_handler",
                    trigger_bucket=setting.trigger_bucket_exit,
                    scheduled_local=scheduled_local,
                    now_utc=now_utc,
                    decision="exited",
                    reason="broker_closed",
                    extra={
                        "trade_id": trade_id,
                        "entry_trade_id": entry_trade_id,
                        "exit_price": average_close_price,
                        "exit_price_side": exit_side,
                        "pnl_jpy": realized_pl,
                        "pnl_pips": (
                            pnl_pips(float(state["entry_price"]), average_close_price, setting.side)
                            if state.get("entry_price") is not None and average_close_price is not None
                            else None
                        ),
                    },
                )
                results.append({"setting_id": setting.setting_id, "status": "exited", "trade_id": trade_id})
                continue

            close_result = None
            for attempt in range(1, config.forced_exit_retry_count + 1):
                try:
                    close_result = oanda_client.close_trade(str(entry_trade_id))
                    break
                except OandaApiError:
                    open_trades = oanda_client.get_open_trades(setting.instrument)
                    still_open = any(str(item.get("id")) == str(entry_trade_id) for item in open_trades)
                    if not still_open:
                        break
                    if attempt == config.forced_exit_retry_count:
                        raise
            aws_runtime.update_trade_state(
                trade_id,
                status="exited",
                exit_order_id=close_result.order_id if close_result else None,
                exit_filled_at=(
                    _oanda_fill_time_iso(close_result.raw_response, now_utc.isoformat())
                    if close_result
                    else now_utc.isoformat()
                ),
                exit_price=close_result.fill_price if close_result else None,
                exit_price_side=exit_side,
                exit_reason="forced_exit",
                pnl_jpy=(float(close_result.raw_response["orderFillTransaction"]["pl"]) if close_result and close_result.raw_response.get("orderFillTransaction", {}).get("pl") is not None else None),
                pnl_pips=(pnl_pips(float(state["entry_price"]), float(close_result.fill_price), setting.side) if state.get("entry_price") is not None and close_result and close_result.fill_price is not None else None),
                scheduled_exit_at_utc=now_utc.isoformat(),
                updated_at=now_utc.isoformat(),
            )
            emit_log("SETTING_EXIT", setting_id=setting.setting_id, trade_id=trade_id, entry_trade_id=entry_trade_id, exit_order_id=close_result.order_id if close_result else None, exit_price=close_result.fill_price if close_result else None, exit_price_side=exit_side, exit_reason="forced_exit")
            _record_decision(
                aws_runtime=aws_runtime,
                setting=setting,
                handler_name="forced_exit_handler",
                trigger_bucket=setting.trigger_bucket_exit,
                scheduled_local=scheduled_local,
                now_utc=now_utc,
                decision="exited",
                reason="forced_exit",
                extra={
                    "trade_id": trade_id,
                    "entry_trade_id": entry_trade_id,
                    "exit_order_id": close_result.order_id if close_result else None,
                    "exit_price": close_result.fill_price if close_result else None,
                    "exit_price_side": exit_side,
                    "pnl_jpy": (
                        float(close_result.raw_response["orderFillTransaction"]["pl"])
                        if close_result and close_result.raw_response.get("orderFillTransaction", {}).get("pl") is not None
                        else None
                    ),
                    "pnl_pips": (
                        pnl_pips(float(state["entry_price"]), float(close_result.fill_price), setting.side)
                        if state.get("entry_price") is not None and close_result and close_result.fill_price is not None
                        else None
                    ),
                },
            )
            results.append({"setting_id": setting.setting_id, "status": "exited", "trade_id": trade_id})
        except Exception as exc:  # noqa: BLE001
            if trade_id_for_error:
                aws_runtime.update_trade_state(trade_id_for_error, status="exit_failed", updated_at=now_utc.isoformat())
            emit_log("SETTING_ERROR", setting_id=setting.setting_id, error=str(exc), traceback=traceback.format_exc())
            _record_decision(aws_runtime=aws_runtime, setting=setting, handler_name="forced_exit_handler", trigger_bucket=setting.trigger_bucket_exit, scheduled_local=scheduled_local, now_utc=now_utc, decision="exit_failed", reason="exception", extra={"trade_id": trade_id_for_error})
            results.append({"setting_id": setting.setting_id, "status": "error", "error": str(exc)})

    return HandlerResult(status="ok", message="forced exit handler processed", details={"trigger": asdict(trigger), "result_count": len(results), "results": results}).to_dict()
