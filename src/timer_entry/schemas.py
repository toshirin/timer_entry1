from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from typing import Any, Literal

from .filters import runtime_filter_dicts
from .time_utils import JST_TZ, LONDON_TZ


Side = Literal["buy", "sell"]
MarketTz = Literal["Asia/Tokyo", "Europe/London"]


def _market_session_from_tz(market_tz: str) -> str:
    if market_tz == JST_TZ:
        return "tokyo"
    if market_tz == LONDON_TZ:
        return "london"
    return "custom"


def _normalize_clock_hhmm(clock_hhmm: str) -> str:
    parts = clock_hhmm.split(":")
    if len(parts) != 2:
        raise ValueError(f"Clock must be HH:MM format: {clock_hhmm}")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"Clock out of range: {clock_hhmm}")
    return f"{hour:02d}:{minute:02d}"


def _bucket_clock(clock_hhmm: str) -> str:
    return _normalize_clock_hhmm(clock_hhmm).replace(":", "")


def _trigger_bucket(prefix: str, market_tz: str, clock_hhmm: str) -> str:
    return f"{prefix}#{market_tz}#{_bucket_clock(clock_hhmm)}"


def _json_text_or_none(value: dict[str, Any] | list[dict[str, Any]] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class BacktestTrade:
    # 1 trade を scan / qualify / ops で共通に扱える最小単位。
    # series 名もここへ残しておくと、後から約定ロジックを追いやすい。
    trade_id: str
    date_local: str
    side: Side
    entry_time: str
    entry_price: float
    exit_time: str
    exit_price: float
    exit_reason: str
    pnl_pips: float
    hold_minutes: int | None
    entry_price_series: str
    exit_price_series: str
    tp_price_series: str | None = None
    sl_price_series: str | None = None
    forced_exit_price_series: str | None = None
    filter_label: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class BacktestSummary:
    # 研究系の summary.csv をまとめる標準形。
    # 基本 KPI は固定し、それ以外は extra_metrics へ逃がす。
    trade_count: int
    gross_pips: float
    mean_pips: float
    median_pips: float
    std_pips: float
    win_rate: float
    profit_factor: float
    max_dd_pips: float
    annualized_pips: float
    eligible_day_count: int | None = None
    filter_label: str | None = None
    segment_label: str | None = None
    extra_metrics: dict[str, float | int | str | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        extra = data.pop("extra_metrics")
        if isinstance(extra, dict):
            data.update(extra)
        return data


@dataclass(frozen=True)
class SanitySummary:
    # series 使用実績と危険信号を標準化する。
    # Bid / Ask 規約監査と、時刻復元・重複時計監査の両方をここへ寄せる。
    entry_price_series: str
    tp_price_series: str
    sl_price_series: str
    forced_exit_price_series: str
    entry_equals_exit_count: int = 0
    entry_equals_exit_sl_count: int = 0
    same_bar_conflict_count: int = 0
    same_bar_unresolved_count: int = 0
    forced_exit_count: int = 0
    forced_exit_missing_count: int = 0
    feature_skip_count: int = 0
    time_jst_fallback_count: int = 0
    duplicate_clock_removed_count: int = 0
    notes: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeConfig:
    # runtime 側がそのまま consume できる設定形。
    # 旧 SettingConfig と揃え、JSON 直出ししやすくする。
    setting_id: str
    enabled: bool
    strategy_id: str
    slot_id: str
    market_session: str
    market_tz: str
    instrument: str
    side: Side
    entry_clock_local: str
    forced_exit_clock_local: str
    trigger_bucket_entry: str
    trigger_bucket_exit: str
    fixed_units: int | None
    margin_ratio_target: float | None
    size_scale_pct: float | None
    tp_pips: float
    sl_pips: float
    research_label: str | None
    market_open_check_seconds: int
    max_concurrent_positions: int | None
    kill_switch_dd_pct: float | None
    kill_switch_reference_balance_jpy: float | None
    min_maintenance_margin_pct: float | None
    filter_spec_json: str | None
    execution_spec_json: str | None
    notes: str | None

    def to_runtime_json_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_runtime_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_runtime_json_dict(), ensure_ascii=False, indent=indent)


@dataclass(frozen=True)
class StrategySetting:
    # scan / qualify / runtime をまたぐ中心 schema。
    # runtime 固有の項目も抱えておき、最後に RuntimeConfig へ落とせるようにする。
    setting_id: str
    slot_id: str
    side: Side
    market_tz: MarketTz
    entry_clock_local: str
    forced_exit_clock_local: str
    tp_pips: float
    sl_pips: float
    filter_labels: tuple[str, ...] = ()
    pre_range_threshold: float | None = None
    dynamic_filter_threshold: float | None = None
    enabled: bool = True
    strategy_id: str | None = None
    market_session: str | None = None
    instrument: str = "USD_JPY"
    exclude_windows: tuple[str, ...] = ()
    fixed_units: int | None = 10
    margin_ratio_target: float | None = None
    size_scale_pct: float | None = None
    research_label: str | None = None
    market_open_check_seconds: int = 10
    max_concurrent_positions: int | None = 1
    kill_switch_dd_pct: float | None = -0.2
    kill_switch_reference_balance_jpy: float | None = 100000.0
    min_maintenance_margin_pct: float | None = 150.0
    execution_spec: dict[str, Any] | None = None
    notes: str | None = None

    def normalized_entry_clock(self) -> str:
        return _normalize_clock_hhmm(self.entry_clock_local)

    def normalized_forced_exit_clock(self) -> str:
        return _normalize_clock_hhmm(self.forced_exit_clock_local)

    def resolved_strategy_id(self) -> str:
        if self.strategy_id:
            return self.strategy_id
        return f"timed_entry_{self.side}"

    def resolved_market_session(self) -> str:
        if self.market_session:
            return self.market_session
        return _market_session_from_tz(self.market_tz)

    def runtime_filter_specs(self) -> list[dict[str, object]]:
        return runtime_filter_dicts(
            list(self.filter_labels),
            pre_range_threshold=self.pre_range_threshold,
            dynamic_threshold=self.dynamic_filter_threshold,
        )

    def to_runtime_config(self) -> RuntimeConfig:
        execution_spec = dict(self.execution_spec or {})
        if self.exclude_windows:
            execution_spec.setdefault("exclude_windows", list(self.exclude_windows))

        entry_clock_local = self.normalized_entry_clock()
        forced_exit_clock_local = self.normalized_forced_exit_clock()

        return RuntimeConfig(
            setting_id=self.setting_id,
            enabled=bool(self.enabled),
            strategy_id=self.resolved_strategy_id(),
            slot_id=self.slot_id,
            market_session=self.resolved_market_session(),
            market_tz=self.market_tz,
            instrument=self.instrument,
            side=self.side,
            entry_clock_local=entry_clock_local,
            forced_exit_clock_local=forced_exit_clock_local,
            trigger_bucket_entry=_trigger_bucket("ENTRY", self.market_tz, entry_clock_local),
            trigger_bucket_exit=_trigger_bucket("EXIT", self.market_tz, forced_exit_clock_local),
            fixed_units=self.fixed_units,
            margin_ratio_target=self.margin_ratio_target,
            size_scale_pct=self.size_scale_pct,
            tp_pips=float(self.tp_pips),
            sl_pips=float(self.sl_pips),
            research_label=self.research_label,
            market_open_check_seconds=int(self.market_open_check_seconds),
            max_concurrent_positions=self.max_concurrent_positions,
            kill_switch_dd_pct=self.kill_switch_dd_pct,
            kill_switch_reference_balance_jpy=self.kill_switch_reference_balance_jpy,
            min_maintenance_margin_pct=self.min_maintenance_margin_pct,
            filter_spec_json=_json_text_or_none(self.runtime_filter_specs()),
            execution_spec_json=_json_text_or_none(execution_spec if execution_spec else None),
            notes=self.notes,
        )

    def to_runtime_json_dict(self) -> dict[str, object]:
        return self.to_runtime_config().to_runtime_json_dict()


@dataclass(frozen=True)
class ScanCandidate:
    # scan の候補行を runtime 化しやすい形で持つ。
    # summary は別 dataclass に分け、候補の意味と評価結果を切り離す。
    candidate_id: str
    session_label: str
    side: Side
    market_tz: MarketTz
    entry_clock_local: str
    forced_exit_clock_local: str
    tp_pips: float
    sl_pips: float
    filter_labels: tuple[str, ...] = ()
    pre_range_threshold: float | None = None
    dynamic_filter_threshold: float | None = None
    summary: BacktestSummary | None = None
    research_label: str | None = None
    notes: str | None = None

    def to_strategy_setting(
        self,
        *,
        setting_id: str | None = None,
        slot_id: str | None = None,
        fixed_units: int | None = 10,
    ) -> StrategySetting:
        return StrategySetting(
            setting_id=setting_id or self.candidate_id,
            slot_id=slot_id or self.session_label,
            side=self.side,
            market_tz=self.market_tz,
            entry_clock_local=self.entry_clock_local,
            forced_exit_clock_local=self.forced_exit_clock_local,
            tp_pips=self.tp_pips,
            sl_pips=self.sl_pips,
            filter_labels=self.filter_labels,
            pre_range_threshold=self.pre_range_threshold,
            dynamic_filter_threshold=self.dynamic_filter_threshold,
            fixed_units=fixed_units,
            research_label=self.research_label,
            notes=self.notes,
        )

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        summary = data.get("summary")
        if isinstance(self.summary, BacktestSummary):
            data["summary"] = self.summary.to_dict()
        else:
            data["summary"] = summary
        return data


@dataclass(frozen=True)
class QualifyScenario:
    # qualify の各実験条件を共通化する。
    # base_setting を主語にすると、scan 由来でも手動候補でも同じ流れに乗せやすい。
    scenario_id: str
    experiment_code: str
    base_setting: StrategySetting
    date_from: str | None = None
    date_to: str | None = None
    slippage_mode: str | None = None
    fixed_slippage_pips: float | None = None
    entry_delay_seconds: int | None = None
    risk_fraction: float | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["base_setting"] = asdict(self.base_setting)
        return data


__all__ = [
    "BacktestSummary",
    "BacktestTrade",
    "MarketTz",
    "QualifyScenario",
    "RuntimeConfig",
    "SanitySummary",
    "ScanCandidate",
    "Side",
    "StrategySetting",
]
