from __future__ import annotations

import json
from pathlib import Path


def ensure_run_layout(run_dir: str | Path) -> dict[str, Path]:
    root = Path(run_dir)
    root.mkdir(parents=True, exist_ok=True)
    return {
        "root": root,
        "metadata_json": root / "metadata.json",
        "params_json": root / "params.json",
        "summary_csv": root / "summary.csv",
        "split_summary_csv": root / "split_summary.csv",
        "year_summary_csv": root / "year_summary.csv",
        "trades_csv": root / "trades.csv",
        "sanity_csv": root / "sanity_summary.csv",
    }


def write_json(path: str | Path, payload: object) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
