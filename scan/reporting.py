from __future__ import annotations

import json
from pathlib import Path
import shutil
import zipfile

import pandas as pd


SUMMARY_COLUMNS = [
    "slot_id",
    "side",
    "filter_label",
    "entry_clock_local",
    "sl_pips",
    "tp_pips",
    "trade_count",
    "gross_pips",
    "win_rate",
    "profit_factor",
    "max_dd_pips",
    "max_hold_time_min",
    "same_bar_conflict_count",
    "same_bar_unresolved_count",
    "forced_exit_count",
]


def _markdown_escape(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).replace("|", "\\|")


def _dataframe_to_markdown(df: pd.DataFrame) -> str:
    if df.empty:
        return "No rows."
    columns = [str(col) for col in df.columns]
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = [
        "| " + " | ".join(_markdown_escape(row[col]) for col in df.columns) + " |"
        for _, row in df.iterrows()
    ]
    return "\n".join([header, separator] + rows)


def ensure_run_layout(run_dir: str | Path) -> dict[str, Path]:
    root = Path(run_dir)
    per_slot_dir = root / "per_slot"
    reports_dir = root / "reports"
    root.mkdir(parents=True, exist_ok=True)
    per_slot_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    return {
        "root": root,
        "summary_csv": root / "summary.csv",
        "per_slot_dir": per_slot_dir,
        "reports_dir": reports_dir,
        "metadata_json": root / "metadata.json",
        "report_zip": root / "report.zip",
    }


def write_metadata(run_dir: str | Path, metadata: dict[str, object]) -> Path:
    paths = ensure_run_layout(run_dir)
    path = paths["metadata_json"]
    path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def append_summary_rows(run_dir: str | Path, summary_df: pd.DataFrame) -> None:
    if summary_df.empty:
        return

    paths = ensure_run_layout(run_dir)
    summary_csv = paths["summary_csv"]
    per_slot_dir = paths["per_slot_dir"]

    ordered = summary_df.copy()
    ordered = ordered.loc[:, [col for col in SUMMARY_COLUMNS if col in ordered.columns]]
    ordered.to_csv(summary_csv, mode="a", header=not summary_csv.exists(), index=False)

    for slot_id, slot_df in ordered.groupby("slot_id", sort=False):
        slot_path = per_slot_dir / f"summary_{slot_id}.csv"
        slot_df.to_csv(slot_path, mode="a", header=not slot_path.exists(), index=False)


def _select_primary_secondary(df: pd.DataFrame) -> tuple[pd.Series | None, pd.Series | None]:
    if df.empty:
        return None, None
    ranked = df.sort_values(
        ["gross_pips", "profit_factor", "max_dd_pips", "trade_count"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)
    primary = ranked.iloc[0]
    secondary_pool = ranked[ranked["entry_clock_local"] != primary["entry_clock_local"]]
    secondary = secondary_pool.iloc[0] if not secondary_pool.empty else None
    return primary, secondary


def _candidate_block(title: str, row: pd.Series | None) -> list[str]:
    if row is None:
        return [f"### {title}", "", "- none", ""]
    return [
        f"### {title}",
        "",
        f"- entry_clock_local: {row['entry_clock_local']}",
        f"- filter_label: {row['filter_label']}",
        f"- sl/tp: {int(row['sl_pips'])}/{int(row['tp_pips'])}",
        f"- gross_pips: {float(row['gross_pips']):.6f}",
        f"- trade_count: {int(row['trade_count'])}",
        f"- win_rate: {float(row['win_rate']):.6f}",
        f"- profit_factor: {float(row['profit_factor']):.6f}" if pd.notna(row["profit_factor"]) else "- profit_factor: nan",
        f"- max_dd_pips: {float(row['max_dd_pips']):.6f}" if pd.notna(row["max_dd_pips"]) else "- max_dd_pips: nan",
        f"- max_hold_time_min: {int(row['max_hold_time_min'])}" if pd.notna(row["max_hold_time_min"]) else "- max_hold_time_min: nan",
        f"- same_bar_conflict_count: {int(row['same_bar_conflict_count'])}",
        f"- same_bar_unresolved_count: {int(row['same_bar_unresolved_count'])}",
        "",
    ]


def build_slot_reports(run_dir: str | Path) -> list[Path]:
    paths = ensure_run_layout(run_dir)
    summary_csv = paths["summary_csv"]
    reports_dir = paths["reports_dir"]
    if not summary_csv.exists():
        return []

    summary_df = pd.read_csv(summary_csv)
    created: list[Path] = []
    for slot_id, slot_df in summary_df.groupby("slot_id", sort=True):
        lines: list[str] = [f"# {slot_id}", ""]
        for side, side_df in slot_df.groupby("side", sort=True):
            primary, secondary = _select_primary_secondary(side_df)
            lines.append(f"## {side}")
            lines.append("")
            lines.extend(_candidate_block("primary", primary))
            lines.extend(_candidate_block("secondary", secondary))
        report_path = reports_dir / f"{slot_id}.md"
        report_path.write_text("\n".join(lines), encoding="utf-8")
        created.append(report_path)
    return created


def build_summary_report(run_dir: str | Path) -> Path | None:
    paths = ensure_run_layout(run_dir)
    summary_csv = paths["summary_csv"]
    if not summary_csv.exists():
        return None

    df = pd.read_csv(summary_csv)
    rows: list[dict[str, object]] = []
    for (slot_id, side), group in df.groupby(["slot_id", "side"], sort=True):
        primary, _ = _select_primary_secondary(group)
        rows.append(
            {
                "slot_id": slot_id,
                "side": side,
                "entry_clock_local": primary["entry_clock_local"] if primary is not None else None,
                "filter_label": primary["filter_label"] if primary is not None else None,
                "sl_pips": primary["sl_pips"] if primary is not None else None,
                "tp_pips": primary["tp_pips"] if primary is not None else None,
                "gross_pips": primary["gross_pips"] if primary is not None else None,
                "trade_count": primary["trade_count"] if primary is not None else None,
            }
        )

    out = pd.DataFrame(rows)
    report_path = paths["reports_dir"] / "summary_report.md"
    lines = ["# summary_report", "", _dataframe_to_markdown(out) if not out.empty else "No summary rows."]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def build_report_zip(run_dir: str | Path) -> Path:
    paths = ensure_run_layout(run_dir)
    build_slot_reports(run_dir)
    build_summary_report(run_dir)

    zip_path = paths["report_zip"]
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(paths["root"].rglob("*")):
            if path.is_file() and path != zip_path:
                zf.write(path, arcname=str(path.relative_to(paths["root"])))
    return zip_path


def reset_run_dir(run_dir: str | Path) -> None:
    root = Path(run_dir)
    if root.exists():
        shutil.rmtree(root)
