from __future__ import annotations

from pathlib import Path

import pandas as pd


DEFAULT_TICKS_DIR = Path("ticks") / "USDJPY"


def _to_epoch_us(ts_local: str, market_tz: str) -> int:
    ts = pd.Timestamp(ts_local, tz=market_tz).tz_convert("UTC")
    return int(ts.value // 1_000)


def load_ticks_for_local_day(
    *,
    date_local: str,
    start_time_local: str,
    end_time_local: str,
    market_tz: str,
    ticks_dir: str | Path = DEFAULT_TICKS_DIR,
) -> pd.DataFrame:
    ticks_path = Path(ticks_dir)
    if not ticks_path.exists():
        raise FileNotFoundError(f"tick dataset not found: {ticks_path}")

    try:
        import pyarrow.dataset as ds
    except ImportError as exc:
        raise RuntimeError("pyarrow is required for tick replay") from exc

    start_epoch_us = _to_epoch_us(f"{date_local} {start_time_local}", market_tz)
    end_epoch_us = _to_epoch_us(f"{date_local} {end_time_local}", market_tz)
    if end_epoch_us <= start_epoch_us:
        end_epoch_us = _to_epoch_us(f"{date_local} 23:59:59.999999", market_tz)

    dataset = ds.dataset(ticks_path, format="parquet", partitioning="hive")
    table = dataset.to_table(
        columns=["epoch_us", "bid", "ask"],
        filter=(ds.field("epoch_us") >= start_epoch_us) & (ds.field("epoch_us") < end_epoch_us),
    )
    df = table.to_pandas()
    if df.empty:
        return df
    return df.sort_values("epoch_us").drop_duplicates("epoch_us", keep="first").reset_index(drop=True)
