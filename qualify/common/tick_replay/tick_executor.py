from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from timer_entry.direction import get_direction_spec
from timer_entry.features import PIP_SIZE


@dataclass(frozen=True)
class TickReplayRequest:
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
    slippage_mode: str = "none"
    fixed_slippage_pips: float = 0.0
    entry_delay_seconds: int = 0


def apply_slippage(price: float, side: str, mode: str, fixed_slippage_pips: float) -> float:
    if mode == "none" or fixed_slippage_pips == 0.0:
        return price
    slip = fixed_slippage_pips * PIP_SIZE
    if side == "buy":
        return price + slip
    return price - slip


def _entry_series_name(side: str) -> str:
    return "ask_tick" if side == "buy" else "bid_tick"


def _exit_series_name(side: str) -> str:
    return "bid_tick" if side == "buy" else "ask_tick"


def _tp_series_name(side: str) -> str:
    return "bid_tick/bid_tick" if side == "buy" else "ask_tick/ask_tick"


def _sl_series_name(side: str) -> str:
    return "ask_tick/bid_tick" if side == "buy" else "bid_tick/ask_tick"


def _forced_exit_series_name(side: str) -> str:
    return _exit_series_name(side)


def _epoch_us(local_ts: pd.Timestamp, market_tz: str) -> int:
    return int(pd.Timestamp(local_ts, tz=market_tz).tz_convert("UTC").value // 1_000)


def _build_base_result(request: TickReplayRequest) -> dict[str, object]:
    side = request.side
    return {
        **asdict(request),
        "entry_time": None,
        "entry_price": None,
        "exit_time": None,
        "exit_price": None,
        "exit_reason": None,
        "pnl_pips": None,
        "hold_minutes": None,
        "entry_price_series": _entry_series_name(side),
        "exit_price_series": _exit_series_name(side),
        "tp_price_series": _tp_series_name(side),
        "sl_price_series": _sl_series_name(side),
        "forced_exit_price_series": _forced_exit_series_name(side),
        "entry_equals_exit_sl_flag": False,
        "entry_equals_exit_all_flag": False,
        "entry_bar_exit_flag": False,
        "feature_after_entry_flag": False,
        "series_mismatch_flag": False,
        "forced_exit_missing_flag": False,
        "tp_sl_same_tick_flag": False,
        "tick_not_found_flag": False,
        "entry_after_forced_exit_flag": False,
        "entry_epoch_us": None,
        "exit_epoch_us": None,
        "monitor_start_time_local": None,
    }


def execute_tick_replay(request: TickReplayRequest, ticks: pd.DataFrame) -> dict[str, object]:
    spec = get_direction_spec(request.side)
    scheduled_entry = pd.Timestamp(request.entry_time_local)
    scheduled_forced_exit = pd.Timestamp(request.forced_exit_time_local)
    delayed_entry = scheduled_entry + pd.Timedelta(seconds=request.entry_delay_seconds)
    entry_cutoff = _epoch_us(delayed_entry, request.market_tz)
    forced_cutoff = _epoch_us(scheduled_forced_exit, request.market_tz)

    result = _build_base_result(request)
    post_entry = ticks.loc[ticks["epoch_us"] >= entry_cutoff].reset_index(drop=True)
    if post_entry.empty:
        result["exit_reason"] = "tick_not_found"
        result["tick_not_found_flag"] = True
        return result

    entry_tick = post_entry.iloc[0]
    entry_epoch_us = int(entry_tick["epoch_us"])
    if entry_epoch_us >= forced_cutoff:
        result["exit_reason"] = "entry_after_forced_exit"
        result["entry_after_forced_exit_flag"] = True
        result["entry_epoch_us"] = entry_epoch_us
        result["entry_time"] = (
            pd.to_datetime(entry_epoch_us, unit="us", utc=True).tz_convert(request.market_tz).tz_localize(None).isoformat(sep=" ")
        )
        return result

    raw_entry_price = float(entry_tick[spec.entry_price_side])
    entry_price = apply_slippage(
        raw_entry_price,
        side=spec.side,
        mode=request.slippage_mode,
        fixed_slippage_pips=request.fixed_slippage_pips,
    )
    entry_time_local = pd.to_datetime(entry_epoch_us, unit="us", utc=True).tz_convert(request.market_tz).tz_localize(None)
    monitor_start_local = entry_time_local.floor("min") + pd.Timedelta(minutes=1)
    monitor_start_epoch_us = _epoch_us(monitor_start_local, request.market_tz)
    tp_level = entry_price + spec.tp_sign * request.tp_pips * PIP_SIZE
    sl_level = entry_price + spec.sl_sign * request.sl_pips * PIP_SIZE

    monitoring = post_entry.loc[post_entry["epoch_us"] >= monitor_start_epoch_us].reset_index(drop=True)
    forced_ticks = monitoring.loc[monitoring["epoch_us"] >= forced_cutoff]

    exit_reason = "forced_exit"
    exit_epoch_us: int | None = None
    exit_price: float | None = None
    tp_sl_same_tick_flag = False

    for _, tick in monitoring.iterrows():
        epoch_us = int(tick["epoch_us"])
        if epoch_us >= forced_cutoff:
            break
        tp_hit = float(tick["bid"]) >= tp_level if spec.side == "buy" else float(tick["ask"]) <= tp_level
        sl_hit = float(tick["ask"]) <= sl_level if spec.side == "buy" else float(tick["bid"]) >= sl_level
        if not tp_hit and not sl_hit:
            continue
        if tp_hit and sl_hit:
            tp_sl_same_tick_flag = True
            exit_reason = "sl"
        elif tp_hit:
            exit_reason = "tp"
        else:
            exit_reason = "sl"
        raw_exit_price = float(tick[spec.exit_price_side])
        exit_price = apply_slippage(
            raw_exit_price,
            side="sell" if spec.side == "buy" else "buy",
            mode=request.slippage_mode,
            fixed_slippage_pips=request.fixed_slippage_pips,
        )
        exit_epoch_us = epoch_us
        break

    if exit_epoch_us is None:
        if forced_ticks.empty:
            result.update(
                {
                    "entry_epoch_us": entry_epoch_us,
                    "entry_time": entry_time_local.isoformat(sep=" "),
                    "entry_price": float(entry_price),
                    "exit_reason": "forced_exit_missing",
                    "forced_exit_missing_flag": True,
                    "monitor_start_time_local": monitor_start_local.isoformat(sep=" "),
                }
            )
            return result
        forced_tick = forced_ticks.iloc[0]
        exit_epoch_us = int(forced_tick["epoch_us"])
        raw_exit_price = float(forced_tick[spec.exit_price_side])
        exit_price = apply_slippage(
            raw_exit_price,
            side="sell" if spec.side == "buy" else "buy",
            mode=request.slippage_mode,
            fixed_slippage_pips=request.fixed_slippage_pips,
        )

    assert exit_price is not None
    exit_time_local = pd.to_datetime(exit_epoch_us, unit="us", utc=True).tz_convert(request.market_tz).tz_localize(None)
    pnl_pips = (exit_price - entry_price) / PIP_SIZE if spec.side == "buy" else (entry_price - exit_price) / PIP_SIZE

    result.update(
        {
            "entry_time": entry_time_local.isoformat(sep=" "),
            "entry_price": float(entry_price),
            "exit_time": exit_time_local.isoformat(sep=" "),
            "exit_price": float(exit_price),
            "exit_reason": exit_reason,
            "pnl_pips": round(float(pnl_pips), 6),
            "hold_minutes": int((exit_time_local - entry_time_local).total_seconds() / 60.0),
            "entry_equals_exit_sl_flag": bool(entry_epoch_us == exit_epoch_us and exit_reason == "sl"),
            "entry_equals_exit_all_flag": bool(entry_epoch_us == exit_epoch_us),
            "entry_bar_exit_flag": bool(entry_time_local.floor("min") == exit_time_local.floor("min")),
            "tp_sl_same_tick_flag": tp_sl_same_tick_flag,
            "entry_epoch_us": entry_epoch_us,
            "exit_epoch_us": exit_epoch_us,
            "monitor_start_time_local": monitor_start_local.isoformat(sep=" "),
        }
    )
    return result
