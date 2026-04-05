#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

try:
    import pandas as pd
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "pandas is required. Install it with: pip install pandas"
    ) from exc

try:
    from tqdm import tqdm
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "tqdm is required. Install it with: pip install tqdm"
    ) from exc

try:
    import pyarrow as pa
    import pyarrow.dataset as ds
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "pyarrow is required. Install it with: pip install pyarrow"
    ) from exc


@dataclass
class Stats:
    files_processed: int = 0
    files_skipped: int = 0
    rows_read: int = 0
    rows_written: int = 0
    rows_dropped: int = 0
    years_written: set[int] = field(default_factory=set)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert broker-time tick CSV zip files into yearly partitioned Parquet."
    )
    parser.add_argument("--in-dir", required=True, help="Input directory containing zip files.")
    parser.add_argument("--out-dir", required=True, help="Output directory for Parquet dataset.")
    parser.add_argument("--symbol", required=True, help="Symbol name used in output path.")
    parser.add_argument(
        "--pattern",
        default="ticks_USDJPY-oj5k_*.zip",
        help="Glob pattern under --in-dir for source zip files.",
    )
    parser.add_argument("--sep", default="\t", help="CSV/TSV separator.")
    parser.add_argument(
        "--broker-utc-offset-hours",
        type=int,
        default=3,
        help="Broker wall-clock offset from UTC (e.g. 3 for UTC+3).",
    )
    parser.add_argument(
        "--chunksize",
        type=int,
        default=2_000_000,
        help="Rows per chunk to stream from each csv file.",
    )
    parser.add_argument(
        "--bid-dtype",
        choices=["float32", "float64"],
        default="float64",
        help="Output dtype for bid/ask columns.",
    )
    return parser


def find_inner_csv_name(names: Iterable[str]) -> str | None:
    for name in names:
        if name.endswith("/"):
            continue
        lower = name.lower()
        if lower.endswith(".csv") or lower.endswith(".tsv") or lower.endswith(".txt"):
            return name
    for name in names:
        if not name.endswith("/"):
            return name
    return None


def parse_broker_datetime_to_utc(date_col: pd.Series, time_col: pd.Series, offset_hours: int) -> pd.Series:
    dt_str = date_col.astype("string") + " " + time_col.astype("string")
    ts_local = pd.to_datetime(dt_str, format="%Y.%m.%d %H:%M:%S.%f", errors="coerce")
    missing = ts_local.isna()
    if missing.any():
        ts_local_2 = pd.to_datetime(dt_str[missing], format="%Y.%m.%d %H:%M:%S", errors="coerce")
        ts_local.loc[missing] = ts_local_2
    return ts_local - pd.Timedelta(hours=offset_hours)


def write_chunk_to_dataset(
    frame: pd.DataFrame,
    dataset_dir: Path,
    chunk_idx: int,
) -> None:
    table = pa.Table.from_pandas(frame, preserve_index=False)
    ds.write_dataset(
        data=table,
        base_dir=str(dataset_dir),
        format="parquet",
        partitioning=["year"],
        existing_data_behavior="overwrite_or_ignore",
        basename_template=f"part-{chunk_idx:08d}-{{i}}.parquet",
    )


def process_zip_file(
    zip_path: Path,
    dataset_dir: Path,
    sep: str,
    chunksize: int,
    offset_hours: int,
    bid_dtype: str,
    stats: Stats,
    chunk_counter_start: int,
) -> int:
    try:
        with zipfile.ZipFile(zip_path) as zf:
            inner_name = find_inner_csv_name(zf.namelist())
            if inner_name is None:
                print(f"[skip] no inner file: {zip_path}", file=sys.stderr)
                stats.files_skipped += 1
                return chunk_counter_start

            with zf.open(inner_name, "r") as src:
                reader = pd.read_csv(
                    src,
                    sep=sep,
                    chunksize=chunksize,
                    dtype={
                        "<DATE>": "string",
                        "<TIME>": "string",
                        "<BID>": "float64",
                        "<ASK>": "float64",
                    },
                    usecols=["<DATE>", "<TIME>", "<BID>", "<ASK>"],
                )

                chunk_counter = chunk_counter_start
                for chunk in reader:
                    rows_in = len(chunk)
                    stats.rows_read += rows_in
                    if rows_in == 0:
                        continue

                    ts_utc = parse_broker_datetime_to_utc(
                        chunk["<DATE>"], chunk["<TIME>"], offset_hours
                    )
                    valid = ts_utc.notna() & chunk["<BID>"].notna() & chunk["<ASK>"].notna()

                    if not valid.any():
                        stats.rows_dropped += rows_in
                        continue

                    ts_utc_valid = ts_utc[valid]
                    epoch_us = (ts_utc_valid.astype("int64") // 1_000).astype("int64")
                    years = ts_utc_valid.dt.year.astype("int16")
                    months = ts_utc_valid.dt.month.astype("int8")

                    out = pd.DataFrame(
                        {
                            "epoch_us": epoch_us.to_numpy(dtype="int64", copy=False),
                            "bid": chunk.loc[valid, "<BID>"].to_numpy(dtype=bid_dtype, copy=False),
                            "ask": chunk.loc[valid, "<ASK>"].to_numpy(dtype=bid_dtype, copy=False),
                            "year": years.to_numpy(dtype="int16", copy=False),
                            "month": months.to_numpy(dtype="int8", copy=False),
                        }
                    )

                    write_chunk_to_dataset(out, dataset_dir, chunk_counter)
                    chunk_counter += 1
                    written = len(out)
                    stats.rows_written += written
                    stats.rows_dropped += rows_in - written
                    stats.years_written.update(int(y) for y in pd.unique(out["year"]))

                stats.files_processed += 1
                return chunk_counter

    except zipfile.BadZipFile:
        print(f"[skip] bad zip: {zip_path}", file=sys.stderr)
    except pd.errors.EmptyDataError:
        print(f"[skip] empty csv in zip: {zip_path}", file=sys.stderr)
    except KeyError as exc:
        print(f"[skip] required column missing in {zip_path}: {exc}", file=sys.stderr)
    except Exception as exc:
        print(f"[skip] failed to process {zip_path}: {exc}", file=sys.stderr)

    stats.files_skipped += 1
    return chunk_counter_start


def main() -> int:
    args = build_parser().parse_args()

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    dataset_dir = out_dir / args.symbol
    dataset_dir.mkdir(parents=True, exist_ok=True)

    zip_paths = [Path(p) for p in sorted(glob.glob(str(in_dir / args.pattern)))]
    if not zip_paths:
        print(f"no input files matched: {in_dir / args.pattern}", file=sys.stderr)
        return 1

    sep = args.sep.encode("utf-8").decode("unicode_escape")

    stats = Stats()
    chunk_counter = 0

    file_pbar = tqdm(zip_paths, unit="file", desc="zip files", dynamic_ncols=True)
    for zip_path in file_pbar:
        file_pbar.set_postfix_str(zip_path.name)
        tqdm.write(f"[file] {zip_path.name}")
        chunk_counter = process_zip_file(
            zip_path=zip_path,
            dataset_dir=dataset_dir,
            sep=sep,
            chunksize=args.chunksize,
            offset_hours=args.broker_utc_offset_hours,
            bid_dtype=args.bid_dtype,
            stats=stats,
            chunk_counter_start=chunk_counter,
        )

    years_sorted = sorted(stats.years_written)
    years_str = ",".join(str(y) for y in years_sorted)

    print(f"files_processed={stats.files_processed}")
    print(f"files_skipped={stats.files_skipped}")
    print(f"rows_read={stats.rows_read}")
    print(f"rows_written={stats.rows_written}")
    print(f"rows_dropped={stats.rows_dropped}")
    print(f"years_written={years_str}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
