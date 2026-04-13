from __future__ import annotations

from dataclasses import asdict, dataclass

from timer_entry.backtest_1m import BacktestRunResult, run_backtest_1m
from timer_entry.minute_data import MinuteDataSummary, TradingDay

from ..params import E004Params


@dataclass(frozen=True)
class TickSignalDay:
    trade_id: str
    date_local: str
    year: int
    comparison_label: str
    side: str
    market_tz: str
    filter_label: str
    entry_time_local: str
    forced_exit_time_local: str
    tp_pips: float
    sl_pips: float
    minute_entry_time: str
    minute_entry_price: float
    minute_exit_time: str
    minute_exit_price: float
    minute_exit_reason: str
    minute_pnl_pips: float
    minute_hold_minutes: int | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def generate_e004_signal_days(
    days: list[TradingDay],
    *,
    params: E004Params,
    load_summary: MinuteDataSummary,
    pre_range_threshold: float | None = None,
    dynamic_filter_threshold: float | None = None,
) -> tuple[list[TickSignalDay], BacktestRunResult]:
    setting = params.to_strategy_setting(
        pre_range_threshold=pre_range_threshold,
        dynamic_filter_threshold=dynamic_filter_threshold,
    )
    minute_result = run_backtest_1m(
        days,
        setting,
        time_jst_fallback_count=load_summary.time_jst_fallback_count,
        duplicate_clock_removed_count=load_summary.duplicate_clock_removed_count,
    )
    filter_label = ",".join(params.baseline.filter_labels)
    entry_clock = f"{params.baseline.entry_clock_local}:00"
    forced_exit_clock = f"{params.baseline.forced_exit_clock_local}:00"

    signals = [
        TickSignalDay(
            trade_id=trade.trade_id,
            date_local=trade.date_local,
            year=int(trade.date_local[:4]),
            comparison_label=params.comparison_label(),
            side=params.side,
            market_tz=params.market_tz,
            filter_label=filter_label,
            entry_time_local=f"{trade.date_local} {entry_clock}",
            forced_exit_time_local=f"{trade.date_local} {forced_exit_clock}",
            tp_pips=float(params.baseline.tp_pips),
            sl_pips=float(params.baseline.sl_pips),
            minute_entry_time=trade.entry_time,
            minute_entry_price=float(trade.entry_price),
            minute_exit_time=trade.exit_time,
            minute_exit_price=float(trade.exit_price),
            minute_exit_reason=trade.exit_reason,
            minute_pnl_pips=float(trade.pnl_pips),
            minute_hold_minutes=trade.hold_minutes,
        )
        for trade in minute_result.trades
    ]
    return signals, minute_result
