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
    "trade_count_in",
    "trade_count_out",
    "in_gross_pips",
    "out_gross_pips",
    "gross_pips",
    "rank_in",
    "rank_out",
    "rank_gap_abs",
    "top1_share_of_total",
    "ex_top10_gross_pips",
    "pass_stability_gate",
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
    gate_pass = df[df["pass_stability_gate"]].copy() if "pass_stability_gate" in df.columns else df.iloc[0:0].copy()
    source = gate_pass if not gate_pass.empty else df
    ranked = source.sort_values(
        ["pass_stability_gate", "out_gross_pips", "in_gross_pips", "rank_gap_abs", "ex_top10_gross_pips", "profit_factor", "trade_count"],
        ascending=[False, False, False, True, False, False, False],
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
        f"- pass_stability_gate: {bool(row['pass_stability_gate'])}" if "pass_stability_gate" in row.index else "- pass_stability_gate: n/a",
        f"- in_gross_pips: {float(row['in_gross_pips']):.6f}" if "in_gross_pips" in row.index and pd.notna(row["in_gross_pips"]) else "- in_gross_pips: nan",
        f"- out_gross_pips: {float(row['out_gross_pips']):.6f}" if "out_gross_pips" in row.index and pd.notna(row["out_gross_pips"]) else "- out_gross_pips: nan",
        f"- gross_pips: {float(row['gross_pips']):.6f}",
        f"- rank_in: {float(row['rank_in']):.0f}" if "rank_in" in row.index and pd.notna(row["rank_in"]) else "- rank_in: nan",
        f"- rank_out: {float(row['rank_out']):.0f}" if "rank_out" in row.index and pd.notna(row["rank_out"]) else "- rank_out: nan",
        f"- rank_gap_abs: {float(row['rank_gap_abs']):.0f}" if "rank_gap_abs" in row.index and pd.notna(row["rank_gap_abs"]) else "- rank_gap_abs: nan",
        f"- ex_top10_gross_pips: {float(row['ex_top10_gross_pips']):.6f}" if "ex_top10_gross_pips" in row.index and pd.notna(row["ex_top10_gross_pips"]) else "- ex_top10_gross_pips: nan",
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
                "pass_stability_gate": primary["pass_stability_gate"] if primary is not None and "pass_stability_gate" in primary.index else None,
                "in_gross_pips": primary["in_gross_pips"] if primary is not None and "in_gross_pips" in primary.index else None,
                "out_gross_pips": primary["out_gross_pips"] if primary is not None and "out_gross_pips" in primary.index else None,
                "rank_gap_abs": primary["rank_gap_abs"] if primary is not None and "rank_gap_abs" in primary.index else None,
                "ex_top10_gross_pips": primary["ex_top10_gross_pips"] if primary is not None and "ex_top10_gross_pips" in primary.index else None,
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
