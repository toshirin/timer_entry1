from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from qualify.common.e004 import run_e004
from qualify.common.params import load_e004_params


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run qualify E004 with shared tick replay engine.")
    parser.add_argument("--params-file", required=True, help="Path to ChatGPT-produced JSON params.")
    parser.add_argument("--dataset-dir", default="dataset")
    parser.add_argument("--ticks-dir", default="dataset/ticks/USDJPY")
    parser.add_argument("--out-dir", default="qualify/out/E004/latest")
    parser.add_argument("--years", nargs="+", type=int, default=[2019, 2020, 2021, 2022, 2023, 2024, 2025])
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--allow-gate-fail", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    params = load_e004_params(args.params_file)
    result = run_e004(
        params=params,
        dataset_dir=args.dataset_dir,
        ticks_dir=args.ticks_dir,
        out_dir=args.out_dir,
        years=list(args.years),
        jobs=int(args.jobs),
        allow_gate_fail=bool(args.allow_gate_fail),
    )
    print(f"[WRITE] {args.out_dir}")
    print(f"[SIGNAL_ROWS] {len(result['signal_days_df'])}")
    print(f"[TRADE_ROWS] {len(result['trades_df'])}")


if __name__ == "__main__":
    main()
