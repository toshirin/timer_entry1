from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
from typing import Any

import pandas as pd
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class PortfolioSetting:
    setting_id: str
    enabled: bool
    slot_id: str
    side: str
    market_tz: str
    entry_clock_local: str
    forced_exit_clock_local: str
    trigger_bucket_entry: str
    fixed_units: int | None
    margin_ratio_target: float | None
    size_scale_pct: float | None
    tp_pips: float
    sl_pips: float
    research_label: str | None
    labels: tuple[str, ...]
    min_maintenance_margin_pct: float | None
    unit_level: int | None
    execution_spec: dict[str, Any]
    source_file: str

    @property
    def is_watch(self) -> bool:
        return any(label.strip().lower() == "watch" for label in self.labels)

    @property
    def effective_margin_ratio_target(self) -> float | None:
        if self.margin_ratio_target is not None:
            return self.margin_ratio_target
        selected = self.execution_spec.get("selected_target_maintenance_margin_pct")
        if selected is not None:
            return float(selected)
        if self.min_maintenance_margin_pct is not None:
            return self.min_maintenance_margin_pct
        return None


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _parse_json_object(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    loaded = json.loads(str(value))
    if not isinstance(loaded, dict):
        return {}
    return loaded


def load_settings(config_dir: str | Path, *, include_disabled: bool = False) -> list[PortfolioSetting]:
    settings: list[PortfolioSetting] = []
    for path in sorted(Path(config_dir).glob("*/*.json")):
        item = json.loads(path.read_text())
        enabled = bool(item.get("enabled", False))
        if not enabled and not include_disabled:
            continue
        labels = item.get("labels") or []
        if isinstance(labels, str):
            labels = [labels]
        settings.append(
            PortfolioSetting(
                setting_id=str(item["setting_id"]),
                enabled=enabled,
                slot_id=str(item["slot_id"]),
                side=str(item.get("side", "buy")).lower(),
                market_tz=str(item["market_tz"]),
                entry_clock_local=str(item["entry_clock_local"]),
                forced_exit_clock_local=str(item["forced_exit_clock_local"]),
                trigger_bucket_entry=str(item["trigger_bucket_entry"]),
                fixed_units=_to_int(item.get("fixed_units")),
                margin_ratio_target=_to_float(item.get("margin_ratio_target")),
                size_scale_pct=_to_float(item.get("size_scale_pct")),
                tp_pips=float(item.get("tp_pips", 0.0)),
                sl_pips=float(item.get("sl_pips", 0.0)),
                research_label=item.get("research_label"),
                labels=tuple(str(label) for label in labels),
                min_maintenance_margin_pct=_to_float(item.get("min_maintenance_margin_pct")),
                unit_level=_to_int(item.get("unit_level")),
                execution_spec=_parse_json_object(item.get("execution_spec_json")),
                source_file=str(path),
            )
        )
    return settings


def _source_e004_dir(setting: PortfolioSetting, qualify_out_dir: str | Path) -> Path:
    source_dirs = setting.execution_spec.get("source_output_dirs")
    if isinstance(source_dirs, dict) and source_dirs.get("E004"):
        raw = Path(str(source_dirs["E004"]))
        if raw.exists():
            return raw
        # Old promoted configs may contain a generic qualify/out/E004/latest path.
        if setting.slot_id not in raw.parts:
            candidate = Path(qualify_out_dir) / setting.slot_id / "v1" / "E004" / "latest"
            if candidate.exists():
                return candidate
        return raw
    return Path(qualify_out_dir) / setting.slot_id / "v1" / "E004" / "latest"


def trade_file_for_setting(setting: PortfolioSetting, qualify_out_dir: str | Path) -> Path:
    return _source_e004_dir(setting, qualify_out_dir) / "trades.csv"


def _clock_matches(series: pd.Series, clock: str) -> pd.Series:
    return series.astype(str).str[11:16].eq(clock)


def load_setting_trades(
    setting: PortfolioSetting,
    *,
    qualify_out_dir: str | Path,
    date_from: date,
    date_to: date,
) -> pd.DataFrame:
    path = trade_file_for_setting(setting, qualify_out_dir)
    if not path.exists():
        return pd.DataFrame()

    df = pd.read_csv(path)
    if df.empty:
        return df

    required = {"date_local", "side", "entry_time", "exit_time", "entry_price", "exit_price", "pnl_pips"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")

    out = df.copy()
    out["date_local_date"] = pd.to_datetime(out["date_local"], format="mixed").dt.date
    out = out.loc[(out["date_local_date"] >= date_from) & (out["date_local_date"] <= date_to)]
    out = out.loc[out["side"].astype(str).str.lower().eq(setting.side)]
    out = out.loc[pd.to_numeric(out["tp_pips"], errors="coerce").round(6).eq(round(setting.tp_pips, 6))]
    out = out.loc[pd.to_numeric(out["sl_pips"], errors="coerce").round(6).eq(round(setting.sl_pips, 6))]
    if "entry_time_local" in out.columns:
        out = out.loc[_clock_matches(out["entry_time_local"], setting.entry_clock_local)]
    if "forced_exit_time_local" in out.columns:
        out = out.loc[_clock_matches(out["forced_exit_time_local"], setting.forced_exit_clock_local)]
    out = out.loc[pd.to_numeric(out["pnl_pips"], errors="coerce").notna()].copy()
    if out.empty:
        return out

    out["setting_id"] = setting.setting_id
    out["slot_id"] = setting.slot_id
    out["research_label"] = setting.research_label
    out["trigger_bucket_entry"] = setting.trigger_bucket_entry
    out["setting_source_file"] = setting.source_file
    out["trade_source_file"] = str(path)
    out["labels"] = ",".join(setting.labels)
    out["is_watch"] = setting.is_watch
    out["margin_ratio_target"] = setting.effective_margin_ratio_target
    entry_local = pd.to_datetime(out["entry_time"], format="mixed")
    exit_local = pd.to_datetime(out["exit_time"], format="mixed")
    tz = ZoneInfo(setting.market_tz)
    out["entry_ts_local"] = entry_local
    out["exit_ts_local"] = exit_local
    out["entry_ts_utc"] = entry_local.apply(lambda value: value.replace(tzinfo=tz).astimezone(ZoneInfo("UTC")).replace(tzinfo=None))
    out["exit_ts_utc"] = exit_local.apply(lambda value: value.replace(tzinfo=tz).astimezone(ZoneInfo("UTC")).replace(tzinfo=None))
    out["entry_ts"] = out["entry_ts_utc"]
    out["exit_ts"] = out["exit_ts_utc"]
    out["pnl_pips"] = pd.to_numeric(out["pnl_pips"], errors="coerce")
    out["entry_price"] = pd.to_numeric(out["entry_price"], errors="coerce")
    out["exit_price"] = pd.to_numeric(out["exit_price"], errors="coerce")
    return out.reset_index(drop=True)
