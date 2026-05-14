from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from .inputs import PortfolioSetting, load_setting_trades


LEDGER_COLUMNS = [
    "setting_id",
    "slot_id",
    "research_label",
    "side",
    "market_tz",
    "date_local",
    "entry_time",
    "exit_time",
    "entry_ts_local",
    "exit_ts_local",
    "entry_ts_utc",
    "exit_ts_utc",
    "entry_ts",
    "exit_ts",
    "entry_price",
    "exit_price",
    "pnl_pips",
    "tp_pips",
    "sl_pips",
    "exit_reason",
    "trigger_bucket_entry",
    "labels",
    "is_watch",
    "margin_ratio_target",
    "trade_source_file",
]


def build_trade_ledger(
    settings: list[PortfolioSetting],
    *,
    qualify_out_dir: str | Path,
    date_from: date,
    date_to: date,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    input_rows: list[dict[str, object]] = []
    for setting in settings:
        trades = load_setting_trades(
            setting,
            qualify_out_dir=qualify_out_dir,
            date_from=date_from,
            date_to=date_to,
        )
        input_rows.append(
            {
                "setting_id": setting.setting_id,
                "slot_id": setting.slot_id,
                "side": setting.side,
                "enabled": setting.enabled,
                "is_watch": setting.is_watch,
                "margin_ratio_target": setting.effective_margin_ratio_target,
                "trade_count": int(len(trades)),
            }
        )
        if not trades.empty:
            frames.append(trades)

    if not frames:
        return pd.DataFrame(columns=LEDGER_COLUMNS), pd.DataFrame(input_rows)

    ledger = pd.concat(frames, ignore_index=True)
    available = [column for column in LEDGER_COLUMNS if column in ledger.columns]
    ledger = ledger[available].copy()
    ledger = ledger.drop_duplicates(subset=["setting_id", "date_local", "entry_time", "exit_time"])
    ledger = ledger.sort_values(["entry_ts_utc", "trigger_bucket_entry", "setting_id"]).reset_index(drop=True)
    return ledger, pd.DataFrame(input_rows)
