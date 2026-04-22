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


def _optional_float(data: dict[str, Any], key: str) -> float | None:
    return float(data[key]) if data.get(key) is not None else None


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    raise ValueError(f"string array is required: {value!r}")


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
    labels: tuple[str, ...]
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
    labels: tuple[str, ...] = ()
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
            labels=self.labels,
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
    target_maintenance_margin_pct: float | None = None
    risk_fraction: float | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["base_setting"] = asdict(self.base_setting)
        return data


@dataclass(frozen=True)
class QualifyPromotionResult:
    # E008 合格後に runtime 昇格判断を固定する成果物。
    # params は実験入力、こちらは安全性確認済みの結果として扱う。
    result_type: str
    schema_version: int
    result_id: str
    slot_id: str
    side: Side
    market_tz: MarketTz
    entry_clock_local: str
    forced_exit_clock_local: str
    tp_pips: float
    sl_pips: float
    filter_labels: tuple[str, ...]
    pass_stability_gate: bool
    e004_passed: bool
    e005_passed: bool
    e006_passed: bool
    e007_passed: bool
    e008_passed: bool
    approved_for_runtime: bool
    selected_target_maintenance_margin_pct: float | None = None
    selected_risk_fraction: float | None = None
    kill_switch_dd_pct: float | None = -0.2
    min_maintenance_margin_pct: float | None = 150.0
    initial_capital_jpy: float | None = 100000.0
    final_equity_jpy: float | None = None
    annualized_pips: float | None = None
    cagr: float | None = None
    trade_rate: float | None = None
    gross_pips: float | None = None
    in_gross_pips: float | None = None
    out_gross_pips: float | None = None
    win_rate: float | None = None
    labels: tuple[str, ...] = ()
    source_params_files: dict[str, str] = field(default_factory=dict)
    source_output_dirs: dict[str, str] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    notes: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QualifyPromotionResult":
        result_type = str(data["result_type"])
        if result_type != "qualify_promotion_result":
            raise ValueError(f"Unsupported qualify promotion result_type: {result_type}")
        filter_labels = tuple(str(label) for label in data.get("filter_labels", []))
        if not filter_labels:
            raise ValueError("filter_labels must not be empty")
        labels = _string_tuple(data.get("labels"))
        return cls(
            result_type=result_type,
            schema_version=int(data["schema_version"]),
            result_id=str(data["result_id"]),
            slot_id=str(data["slot_id"]),
            side=str(data["side"]),  # type: ignore[arg-type]
            market_tz=str(data["market_tz"]),  # type: ignore[arg-type]
            entry_clock_local=str(data["entry_clock_local"]),
            forced_exit_clock_local=str(data["forced_exit_clock_local"]),
            tp_pips=float(data["tp_pips"]),
            sl_pips=float(data["sl_pips"]),
            filter_labels=filter_labels,
            pass_stability_gate=bool(data["pass_stability_gate"]),
            e004_passed=bool(data["e004_passed"]),
            e005_passed=bool(data["e005_passed"]),
            e006_passed=bool(data["e006_passed"]),
            e007_passed=bool(data["e007_passed"]),
            e008_passed=bool(data["e008_passed"]),
            approved_for_runtime=bool(data["approved_for_runtime"]),
            selected_target_maintenance_margin_pct=_optional_float(
                data,
                "selected_target_maintenance_margin_pct",
            ),
            selected_risk_fraction=_optional_float(data, "selected_risk_fraction"),
            kill_switch_dd_pct=_optional_float(data, "kill_switch_dd_pct"),
            min_maintenance_margin_pct=_optional_float(data, "min_maintenance_margin_pct"),
            initial_capital_jpy=_optional_float(data, "initial_capital_jpy"),
            final_equity_jpy=_optional_float(data, "final_equity_jpy"),
            annualized_pips=_optional_float(data, "annualized_pips"),
            cagr=_optional_float(data, "cagr"),
            trade_rate=_optional_float(data, "trade_rate"),
            gross_pips=_optional_float(data, "gross_pips"),
            in_gross_pips=_optional_float(data, "in_gross_pips"),
            out_gross_pips=_optional_float(data, "out_gross_pips"),
            win_rate=_optional_float(data, "win_rate"),
            labels=labels,
            source_params_files=dict(data.get("source_params_files", {})),
            source_output_dirs=dict(data.get("source_output_dirs", {})),
            evidence=dict(data.get("evidence", {})),
            notes=str(data["notes"]) if data.get("notes") is not None else None,
        )

    def assert_promotable(self) -> None:
        if self.tp_pips <= 0:
            raise ValueError("tp_pips must be greater than zero before promotion")
        if self.sl_pips <= 0:
            raise ValueError("sl_pips must be greater than zero before promotion")
        if not self.approved_for_runtime:
            raise ValueError("approved_for_runtime must be true before promotion")
        if not self.pass_stability_gate:
            raise ValueError("pass_stability_gate must be true before promotion")
        failed = [
            code
            for code, passed in (
                ("E004", self.e004_passed),
                ("E005", self.e005_passed),
                ("E006", self.e006_passed),
                ("E007", self.e007_passed),
                ("E008", self.e008_passed),
            )
            if not passed
        ]
        if failed:
            raise ValueError(f"qualify checks must pass before promotion: {failed}")
        if self.kill_switch_dd_pct is None:
            raise ValueError("kill_switch_dd_pct must be set before promotion")
        if self.min_maintenance_margin_pct is None:
            raise ValueError("min_maintenance_margin_pct must be set before promotion")
        if self.initial_capital_jpy is None:
            raise ValueError("initial_capital_jpy must be set before promotion")
        required_metric_names = (
            "selected_target_maintenance_margin_pct",
            "final_equity_jpy",
            "min_maintenance_margin_pct",
            "annualized_pips",
            "cagr",
            "trade_rate",
            "gross_pips",
            "in_gross_pips",
            "out_gross_pips",
            "win_rate",
        )
        missing_metrics = [name for name in required_metric_names if getattr(self, name) is None]
        if self.selected_target_maintenance_margin_pct is None and self.selected_risk_fraction is not None:
            missing_metrics = [name for name in missing_metrics if name != "selected_target_maintenance_margin_pct"]
        if missing_metrics:
            raise ValueError(f"promotion result metrics must be set before promotion: {missing_metrics}")

    def to_strategy_setting(self) -> StrategySetting:
        return StrategySetting(
            setting_id=f"{self.slot_id}_{self.side}_runtime_v1",
            slot_id=self.slot_id,
            side=self.side,
            market_tz=self.market_tz,
            entry_clock_local=self.entry_clock_local,
            forced_exit_clock_local=self.forced_exit_clock_local,
            tp_pips=self.tp_pips,
            sl_pips=self.sl_pips,
            filter_labels=self.filter_labels,
            research_label=self.result_id,
            labels=self.labels,
            notes=self.notes,
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


__all__ = [
    "BacktestSummary",
    "BacktestTrade",
    "MarketTz",
    "QualifyPromotionResult",
    "QualifyScenario",
    "RuntimeConfig",
    "SanitySummary",
    "ScanCandidate",
    "Side",
    "StrategySetting",
]
