from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from .tick_executor import TickReplayRequest, execute_tick_replay
from .tick_io import load_ticks_for_local_day


def _run_signal(request_dict: dict[str, object]) -> dict[str, object]:
    ticks = load_ticks_for_local_day(
        date_local=str(request_dict["date_local"]),
        start_time_local=str(request_dict["entry_time_local"]).split(" ", 1)[1],
        end_time_local="23:59:59.999999",
        market_tz=str(request_dict["market_tz"]),
        ticks_dir=Path(str(request_dict["ticks_dir"])),
    )
    payload = {key: value for key, value in request_dict.items() if key != "ticks_dir"}
    request = TickReplayRequest(**payload)
    return execute_tick_replay(request, ticks)


def _run_requests_sequentially(
    requests: list[dict[str, object]],
    *,
    desc: str,
) -> list[dict[str, object]]:
    trades: list[dict[str, object]] = []
    for request in tqdm(requests, desc=desc, unit="day", mininterval=0.5):
        trades.append(_run_signal(request))
    return trades


def run_tick_replay_batch(
    signal_rows: list[dict[str, object]],
    *,
    ticks_dir: str | Path,
    jobs: int = 1,
    slippage_mode: str = "none",
    fixed_slippage_pips: float = 0.0,
    entry_delay_seconds: int = 0,
) -> pd.DataFrame:
    requests = [
        {
            "trade_id": row["trade_id"],
            "date_local": row["date_local"],
            "year": row["year"],
            "comparison_label": row["comparison_label"],
            "side": row["side"],
            "market_tz": row["market_tz"],
            "filter_label": row["filter_label"],
            "entry_time_local": row["entry_time_local"],
            "forced_exit_time_local": row["forced_exit_time_local"],
            "tp_pips": row["tp_pips"],
            "sl_pips": row["sl_pips"],
            "slippage_mode": slippage_mode,
            "fixed_slippage_pips": fixed_slippage_pips,
            "entry_delay_seconds": entry_delay_seconds,
            "ticks_dir": str(ticks_dir),
        }
        for row in signal_rows
    ]

    trades: list[dict[str, object]] = []
    if jobs == 1:
        trades = _run_requests_sequentially(requests, desc="tick replay")
    else:
        try:
            with ProcessPoolExecutor(max_workers=jobs) as pool:
                futures = [pool.submit(_run_signal, request) for request in requests]
                for future in tqdm(
                    as_completed(futures),
                    total=len(futures),
                    desc="tick replay",
                    unit="day",
                    mininterval=0.5,
                ):
                    trades.append(future.result())
        except BrokenProcessPool:
            print("[WARN] tick replay worker crashed; retrying sequentially with jobs=1")
            trades = _run_requests_sequentially(requests, desc="tick replay fallback")
    return pd.DataFrame(trades)
