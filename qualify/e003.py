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

from qualify.common.e003 import run_e003
from qualify.common.params import load_e003_params


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run qualify E003 with canonical backtest_1m engine.")
    parser.add_argument("--params-file", required=True, help="Path to ChatGPT-produced JSON params.")
    parser.add_argument("--dataset-dir", default="dataset")
    parser.add_argument("--out-dir", default="qualify/out/E003/latest")
    parser.add_argument("--years", nargs="+", type=int, default=[2019, 2020, 2021, 2022, 2023, 2024, 2025])
    parser.add_argument("--allow-gate-fail", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    params = load_e003_params(args.params_file)
    print(f"[START] E003 params={args.params_file} out={args.out_dir}")
    print(f"[YEARS] {' '.join(str(year) for year in args.years)}")
    print(f"[COMPARISONS] {len(params.forced_exit_values)} clocks")
    result = run_e003(
        params=params,
        dataset_dir=args.dataset_dir,
        out_dir=args.out_dir,
        years=list(args.years),
        allow_gate_fail=bool(args.allow_gate_fail),
    )
    print(f"[WRITE] {args.out_dir}")
    print(f"[SUMMARY_ROWS] {len(result['summary_df'])}")
    print(f"[TRADE_ROWS] {len(result['trades_df'])}")


if __name__ == "__main__":
    main()
