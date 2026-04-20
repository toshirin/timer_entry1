from __future__ import annotations

import argparse
import gc
from pathlib import Path
import sys

import pandas as pd
from tqdm import tqdm

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from timer_entry.backtest_fast import compute_fast_feature_row, preprocess_fast_days, run_scan_fast
from timer_entry.minute_data import load_trading_days

from reporting import append_summary_rows, build_report_zip, reset_run_dir, write_metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run timer_entry scan with fast backtest engine.")
    parser.add_argument("--years", nargs="+", type=int, required=True)
    parser.add_argument("--dataset-dir", type=str, default="dataset")
    parser.add_argument("--out-dir", type=str, required=True)
    parser.add_argument("--entry-step-min", type=int, default=5)
    parser.add_argument("--exit-after-min", type=int, default=55)
    parser.add_argument("--sl-grid", nargs="+", type=float, default=[5, 10, 15, 20, 25])
    parser.add_argument("--tp-grid", nargs="+", type=float, default=[5, 10, 15, 20, 25])
    parser.add_argument("--exclude-windows", nargs="*", default=[])
    return parser.parse_args()


def _entry_clocks_for_hour(hour: int, step_min: int) -> list[str]:
    return [f"{hour:02d}:{minute:02d}" for minute in range(0, 60, step_min)]


def _slot_id(prefix: str, hour: int) -> str:
    return f"{prefix}{hour:02d}"


def _session_pairs() -> list[tuple[str, str]]:
    return [
        ("tyo", "Asia/Tokyo"),
        ("lon", "Europe/London"),
    ]


def _compute_pre_range_median(prepared_days: dict[str, object], *, entry_step_min: int) -> float | None:
    values: list[float] = []
    pbar = tqdm(prepared_days.values(), desc="pre_range median", unit="day", leave=False)
    for day in pbar:
        collected_before = len(values)
        session_prefix = "tyo" if day.session_tz == "Asia/Tokyo" else "lon"
        for hour in _hour_range_for_session(session_prefix):
            for clock_hhmm in _entry_clocks_for_hour(hour, entry_step_min):
                entry_idx = day.clock_to_idx.get(clock_hhmm)
                if entry_idx is None:
                    continue
                feature_row = compute_fast_feature_row(day, entry_idx=entry_idx)
                if feature_row.feature_available and pd.notna(feature_row.pre_range_pips):
                    values.append(float(feature_row.pre_range_pips))
        pbar.set_postfix_str(f"date={day.session_date} added={len(values) - collected_before}")
    pbar.close()
    if not values:
        return None
    return float(pd.Series(values, dtype=float).median())


def _hour_range_for_session(session_prefix: str) -> range:
    if session_prefix == "tyo":
        # Tokyo slot は JST 07:00..15:59 の 9 時間帯。
        return range(7, 16)
    if session_prefix == "lon":
        # London slot は London local 08:00..21:59 の 14 時間帯。
        return range(8, 22)
    raise ValueError(f"Unsupported session prefix: {session_prefix}")


def main() -> None:
    args = parse_args()

    reset_run_dir(args.out_dir)
    write_metadata(
        args.out_dir,
        {
            "years": args.years,
            "dataset_dir": args.dataset_dir,
            "entry_step_min": args.entry_step_min,
            "exit_after_min": args.exit_after_min,
            "sl_grid": args.sl_grid,
            "tp_grid": args.tp_grid,
            "exclude_windows": args.exclude_windows,
        },
    )

    for session_prefix, session_tz in _session_pairs():
        print(f"[LOAD] session={session_prefix} tz={session_tz}", flush=True)
        year_days: list[object] = []
        fallback_count = 0
        duplicate_removed_count = 0
        excluded_count = 0
        total_year_count = len(args.years)
        load_pbar = tqdm(args.years, desc=f"load {session_prefix}", unit="year")
        for idx, year in enumerate(load_pbar, start=1):
            trading_days_part, load_summary_part = load_trading_days(
                [year],
                dataset_dir=args.dataset_dir,
                session_tz=session_tz,  # type: ignore[arg-type]
                exclude_windows=args.exclude_windows,
            )
            year_days.extend(trading_days_part)
            fallback_count += load_summary_part.time_jst_fallback_count
            duplicate_removed_count += load_summary_part.duplicate_clock_removed_count
            excluded_count += load_summary_part.excluded_session_day_count
            load_pbar.set_postfix_str(
                f"year={year} days={load_summary_part.session_day_count} "
                f"excluded={load_summary_part.excluded_session_day_count} "
                f"fallback={load_summary_part.time_jst_fallback_count}"
            )
            print(
                f"[LOAD-YEAR] session={session_prefix} {idx}/{total_year_count} "
                f"year={year} days={load_summary_part.session_day_count} "
                f"excluded={load_summary_part.excluded_session_day_count} "
                f"fallback={load_summary_part.time_jst_fallback_count} "
                f"dup_removed={load_summary_part.duplicate_clock_removed_count}",
                flush=True,
            )
        load_pbar.close()

        trading_days = year_days
        total_rows = len(trading_days)
        print(f"[PREP] session={session_prefix} building fast day cache from {total_rows} days", flush=True)
        prepared_days = preprocess_fast_days(trading_days)
        print(f"[PREP] session={session_prefix} fast day cache ready: {len(prepared_days)} days", flush=True)
        print(f"[MEDIAN] session={session_prefix} computing pre_range median", flush=True)
        pre_range_median = _compute_pre_range_median(prepared_days, entry_step_min=args.entry_step_min)
        print(f"[MEDIAN] session={session_prefix} pre_range median={pre_range_median}", flush=True)
        if pre_range_median is None:
            raise RuntimeError(f"pre_range median could not be computed for session={session_prefix}")

        total_slots = len(list(_hour_range_for_session(session_prefix))) * 2
        pbar = tqdm(total=total_slots, desc=f"scan {session_prefix}", unit="slot")
        for hour in _hour_range_for_session(session_prefix):
            slot_id = _slot_id(session_prefix, hour)
            slot_rows: list[pd.DataFrame] = []
            for side in ("buy", "sell"):
                for entry_clock_local in _entry_clocks_for_hour(hour, args.entry_step_min):
                    result = run_scan_fast(
                        prepared_days,
                        slot_id=slot_id,
                        side=side,
                        entry_clock_local=entry_clock_local,
                        exit_after_minutes=args.exit_after_min,
                        sl_grid_pips=args.sl_grid,
                        tp_grid_pips=args.tp_grid,
                        pre_range_median=pre_range_median,
                    )
                    if not result.summary_df.empty:
                        slot_rows.append(result.summary_df)

                pbar.update(1)
                pbar.set_postfix_str(f"slot={slot_id} side={side}")

            if slot_rows:
                slot_summary = pd.concat(slot_rows, ignore_index=True)
                append_summary_rows(args.out_dir, slot_summary)

        pbar.close()
        del prepared_days
        del trading_days
        gc.collect()
        print(
            f"[DONE] session={session_prefix} days={len(year_days)} "
            f"excluded={excluded_count} fallback={fallback_count} dup_removed={duplicate_removed_count}",
            flush=True,
        )

    zip_path = build_report_zip(args.out_dir)
    print(f"[WRITE] {zip_path}", flush=True)


if __name__ == "__main__":
    main()
