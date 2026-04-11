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

from qualify.common.e005_e008 import run_e005_e008
from qualify.common.params import load_e005_e008_params


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run qualify E005-E008 robustness suite.")
    parser.add_argument("--params-file", required=True, help="Path to E005-E008 JSON params.")
    parser.add_argument("--dataset-dir", default="dataset")
    parser.add_argument("--ticks-dir", default="ticks/USDJPY")
    parser.add_argument("--out-dir", default="qualify/out")
    parser.add_argument("--years", nargs="+", type=int, default=[2019, 2020, 2021, 2022, 2023, 2024, 2025])
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--only", nargs="+", choices=["E005", "E006", "E007", "E008"], default=None)
    parser.add_argument("--allow-gate-fail", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    params = load_e005_e008_params(args.params_file)
    print(f"[START] E005-E008 params={args.params_file} out={args.out_dir}")
    print(f"[YEARS] {' '.join(str(year) for year in args.years)}")
    selected = tuple(args.only) if args.only else params.selected_experiments
    print(f"[ONLY] {' '.join(selected)}")
    result = run_e005_e008(
        params=params,
        dataset_dir=args.dataset_dir,
        ticks_dir=args.ticks_dir,
        out_dir=args.out_dir,
        years=list(args.years),
        jobs=int(args.jobs),
        allow_gate_fail=bool(args.allow_gate_fail),
        only=tuple(args.only) if args.only else None,
    )
    for experiment_code, frames in result.items():
        summary_rows = len(frames.get("summary_df", []))
        print(f"[DONE] {experiment_code} summary_rows={summary_rows}")


if __name__ == "__main__":
    main()
