from __future__ import annotations

"""
Collect active qualify result JSON files into a single JSON array or JSONL stream.

Purpose:
- Gather every current result under `qualify/results/`
- Skip anything under `qualify/results/archived/`
- Emit one combined artifact for downstream review or import

Examples:

  python qualify/export_results.py
  python qualify/export_results.py --format jsonl
  python qualify/export_results.py --output qualify/results/all_results.json
  python qualify/export_results.py --format jsonl --output qualify/results/all_results.jsonl
"""

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "qualify" / "results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export active qualify result JSON files as one JSON array or JSONL stream."
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=RESULTS_DIR,
        help="Root directory that contains qualify result JSON files. Default: qualify/results",
    )
    parser.add_argument(
        "--format",
        choices=("json", "jsonl"),
        default="json",
        help="Output format. Default: json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output file. If omitted, write to stdout.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON array output. Ignored for jsonl.",
    )
    return parser.parse_args()


def iter_result_paths(results_dir: Path) -> list[Path]:
    if not results_dir.exists():
        raise FileNotFoundError(f"results directory not found: {results_dir}")

    paths: list[Path] = []
    for path in sorted(results_dir.rglob("*.json")):
        if "archived" in path.parts:
            continue
        paths.append(path)
    return paths


def load_payloads(paths: list[Path]) -> list[object]:
    payloads: list[object] = []
    for path in paths:
        payloads.append(json.loads(path.read_text(encoding="utf-8")))
    return payloads


def render_output(payloads: list[object], output_format: str, pretty: bool) -> str:
    if output_format == "jsonl":
        return "\n".join(json.dumps(payload, ensure_ascii=False) for payload in payloads) + ("\n" if payloads else "")

    indent = 2 if pretty else None
    separators = None if pretty else (",", ":")
    text = json.dumps(payloads, ensure_ascii=False, indent=indent, separators=separators)
    return f"{text}\n"


def write_output(text: str, output_path: Path | None) -> None:
    if output_path is None:
        try:
            sys.stdout.write(text)
        except BrokenPipeError:
            return
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    result_paths = iter_result_paths(args.results_dir)
    payloads = load_payloads(result_paths)
    output_text = render_output(payloads, args.format, args.pretty)
    write_output(output_text, args.output)


if __name__ == "__main__":
    main()
