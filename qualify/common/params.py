from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from timer_entry.filters import get_filter_family
from timer_entry.schemas import StrategySetting


def _market_tz_from_slot(slot_id: str) -> str:
    if slot_id.startswith("tyo"):
        return "Asia/Tokyo"
    if slot_id.startswith("lon"):
        return "Europe/London"
    raise ValueError(f"Unsupported slot prefix for market tz: {slot_id}")


@dataclass(frozen=True)
class BaselineSettingInput:
    entry_clock_local: str
    forced_exit_clock_local: str
    tp_pips: float
    sl_pips: float
    filter_labels: tuple[str, ...]
    exclude_windows: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BaselineSettingInput":
        labels = tuple(str(label) for label in data.get("filter_labels", []))
        if not labels:
            raise ValueError("baseline.filter_labels must not be empty")
        return cls(
            entry_clock_local=str(data["entry_clock_local"]),
            forced_exit_clock_local=str(data["forced_exit_clock_local"]),
            tp_pips=float(data["tp_pips"]),
            sl_pips=float(data["sl_pips"]),
            filter_labels=labels,
            exclude_windows=tuple(str(value) for value in data.get("exclude_windows", [])),
        )


@dataclass(frozen=True)
class E001Params:
    experiment_code: str
    variant_code: str | None
    slot_id: str
    side: str
    baseline: BaselineSettingInput
    comparison_family: str
    comparison_labels: tuple[str, ...]
    pass_stability_gate: bool
    notes: str | None = None
    date_from: str | None = None
    date_to: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "E001Params":
        experiment_code = str(data["experiment_code"])
        if experiment_code != "E001":
            raise ValueError(f"Unsupported experiment_code for E001 runner: {experiment_code}")
        comparison_labels = tuple(str(label) for label in data.get("comparison_labels", []))
        if not comparison_labels:
            raise ValueError("comparison_labels must not be empty")
        comparison_family = str(data["comparison_family"])
        for label in comparison_labels:
            resolved_family = get_filter_family(label)
            if label != "all" and resolved_family != comparison_family:
                raise ValueError(
                    f"comparison label family mismatch: label={label} "
                    f"resolved_family={resolved_family} expected={comparison_family}"
                )
        return cls(
            experiment_code=experiment_code,
            variant_code=str(data["variant_code"]) if data.get("variant_code") is not None else None,
            slot_id=str(data["slot_id"]),
            side=str(data["side"]),
            baseline=BaselineSettingInput.from_dict(dict(data["baseline"])),
            comparison_family=comparison_family,
            comparison_labels=comparison_labels,
            pass_stability_gate=bool(data["pass_stability_gate"]),
            notes=str(data["notes"]) if data.get("notes") is not None else None,
            date_from=str(data["date_from"]) if data.get("date_from") is not None else None,
            date_to=str(data["date_to"]) if data.get("date_to") is not None else None,
        )

    @property
    def market_tz(self) -> str:
        return _market_tz_from_slot(self.slot_id)

    @property
    def run_label(self) -> str:
        return self.variant_code or self.experiment_code

    def to_strategy_setting(
        self,
        *,
        comparison_label: str,
        pre_range_threshold: float | None = None,
        dynamic_filter_threshold: float | None = None,
    ) -> StrategySetting:
        setting_suffix = comparison_label.replace(".", "_")
        return StrategySetting(
            setting_id=f"{self.slot_id}_{self.side}_{self.run_label}_{setting_suffix}",
            slot_id=self.slot_id,
            side=self.side,  # type: ignore[arg-type]
            market_tz=self.market_tz,  # type: ignore[arg-type]
            entry_clock_local=self.baseline.entry_clock_local,
            forced_exit_clock_local=self.baseline.forced_exit_clock_local,
            tp_pips=self.baseline.tp_pips,
            sl_pips=self.baseline.sl_pips,
            filter_labels=(comparison_label,),
            exclude_windows=self.baseline.exclude_windows,
            pre_range_threshold=pre_range_threshold,
            dynamic_filter_threshold=dynamic_filter_threshold,
            notes=self.notes,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class E002Params:
    experiment_code: str
    variant_code: str | None
    slot_id: str
    side: str
    baseline: BaselineSettingInput
    tp_values: tuple[float, ...]
    sl_values: tuple[float, ...]
    pass_stability_gate: bool
    notes: str | None = None
    date_from: str | None = None
    date_to: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "E002Params":
        experiment_code = str(data["experiment_code"])
        if experiment_code != "E002":
            raise ValueError(f"Unsupported experiment_code for E002 runner: {experiment_code}")
        tp_values = tuple(float(value) for value in data.get("tp_values", []))
        sl_values = tuple(float(value) for value in data.get("sl_values", []))
        if not tp_values:
            raise ValueError("tp_values must not be empty")
        if not sl_values:
            raise ValueError("sl_values must not be empty")
        return cls(
            experiment_code=experiment_code,
            variant_code=str(data["variant_code"]) if data.get("variant_code") is not None else None,
            slot_id=str(data["slot_id"]),
            side=str(data["side"]),
            baseline=BaselineSettingInput.from_dict(dict(data["baseline"])),
            tp_values=tp_values,
            sl_values=sl_values,
            pass_stability_gate=bool(data["pass_stability_gate"]),
            notes=str(data["notes"]) if data.get("notes") is not None else None,
            date_from=str(data["date_from"]) if data.get("date_from") is not None else None,
            date_to=str(data["date_to"]) if data.get("date_to") is not None else None,
        )

    @property
    def market_tz(self) -> str:
        return _market_tz_from_slot(self.slot_id)

    @property
    def run_label(self) -> str:
        return self.variant_code or self.experiment_code

    def comparison_label(self, *, tp_pips: float, sl_pips: float) -> str:
        return f"tp{tp_pips:g}_sl{sl_pips:g}"

    def to_strategy_setting(
        self,
        *,
        tp_pips: float,
        sl_pips: float,
        pre_range_threshold: float | None = None,
        dynamic_filter_threshold: float | None = None,
    ) -> StrategySetting:
        comparison_label = self.comparison_label(tp_pips=tp_pips, sl_pips=sl_pips)
        setting_suffix = comparison_label.replace(".", "_")
        return StrategySetting(
            setting_id=f"{self.slot_id}_{self.side}_{self.run_label}_{setting_suffix}",
            slot_id=self.slot_id,
            side=self.side,  # type: ignore[arg-type]
            market_tz=self.market_tz,  # type: ignore[arg-type]
            entry_clock_local=self.baseline.entry_clock_local,
            forced_exit_clock_local=self.baseline.forced_exit_clock_local,
            tp_pips=float(tp_pips),
            sl_pips=float(sl_pips),
            filter_labels=self.baseline.filter_labels,
            exclude_windows=self.baseline.exclude_windows,
            pre_range_threshold=pre_range_threshold,
            dynamic_filter_threshold=dynamic_filter_threshold,
            notes=self.notes,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class E003Params:
    experiment_code: str
    variant_code: str | None
    slot_id: str
    side: str
    baseline: BaselineSettingInput
    forced_exit_values: tuple[str, ...]
    pass_stability_gate: bool
    notes: str | None = None
    date_from: str | None = None
    date_to: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "E003Params":
        experiment_code = str(data["experiment_code"])
        if experiment_code != "E003":
            raise ValueError(f"Unsupported experiment_code for E003 runner: {experiment_code}")
        forced_exit_values = tuple(str(value) for value in data.get("forced_exit_values", []))
        if not forced_exit_values:
            raise ValueError("forced_exit_values must not be empty")
        return cls(
            experiment_code=experiment_code,
            variant_code=str(data["variant_code"]) if data.get("variant_code") is not None else None,
            slot_id=str(data["slot_id"]),
            side=str(data["side"]),
            baseline=BaselineSettingInput.from_dict(dict(data["baseline"])),
            forced_exit_values=forced_exit_values,
            pass_stability_gate=bool(data["pass_stability_gate"]),
            notes=str(data["notes"]) if data.get("notes") is not None else None,
            date_from=str(data["date_from"]) if data.get("date_from") is not None else None,
            date_to=str(data["date_to"]) if data.get("date_to") is not None else None,
        )

    @property
    def market_tz(self) -> str:
        return _market_tz_from_slot(self.slot_id)

    @property
    def run_label(self) -> str:
        return self.variant_code or self.experiment_code

    def comparison_label(self, *, forced_exit_clock_local: str) -> str:
        return f"fx{forced_exit_clock_local.replace(':', '')}"

    def to_strategy_setting(
        self,
        *,
        forced_exit_clock_local: str,
        pre_range_threshold: float | None = None,
        dynamic_filter_threshold: float | None = None,
    ) -> StrategySetting:
        comparison_label = self.comparison_label(forced_exit_clock_local=forced_exit_clock_local)
        setting_suffix = comparison_label.replace(".", "_")
        return StrategySetting(
            setting_id=f"{self.slot_id}_{self.side}_{self.run_label}_{setting_suffix}",
            slot_id=self.slot_id,
            side=self.side,  # type: ignore[arg-type]
            market_tz=self.market_tz,  # type: ignore[arg-type]
            entry_clock_local=self.baseline.entry_clock_local,
            forced_exit_clock_local=forced_exit_clock_local,
            tp_pips=self.baseline.tp_pips,
            sl_pips=self.baseline.sl_pips,
            filter_labels=self.baseline.filter_labels,
            exclude_windows=self.baseline.exclude_windows,
            pre_range_threshold=pre_range_threshold,
            dynamic_filter_threshold=dynamic_filter_threshold,
            notes=self.notes,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _label_fragment(value: str) -> str:
    return value.replace(":", "").replace(".", "_").replace(",", "_").replace(" ", "_")


@dataclass(frozen=True)
class E004Params:
    experiment_code: str
    variant_code: str | None
    slot_id: str
    side: str
    baseline: BaselineSettingInput
    pass_stability_gate: bool
    slippage_mode: str = "none"
    fixed_slippage_pips: float = 0.0
    entry_delay_seconds: int = 0
    notes: str | None = None
    date_from: str | None = None
    date_to: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "E004Params":
        experiment_code = str(data["experiment_code"])
        if experiment_code != "E004":
            raise ValueError(f"Unsupported experiment_code for E004 runner: {experiment_code}")
        return cls(
            experiment_code=experiment_code,
            variant_code=str(data["variant_code"]) if data.get("variant_code") is not None else None,
            slot_id=str(data["slot_id"]),
            side=str(data["side"]),
            baseline=BaselineSettingInput.from_dict(dict(data["baseline"])),
            pass_stability_gate=bool(data["pass_stability_gate"]),
            slippage_mode=str(data.get("slippage_mode", "none")),
            fixed_slippage_pips=float(data.get("fixed_slippage_pips", 0.0)),
            entry_delay_seconds=int(data.get("entry_delay_seconds", 0)),
            notes=str(data["notes"]) if data.get("notes") is not None else None,
            date_from=str(data["date_from"]) if data.get("date_from") is not None else None,
            date_to=str(data["date_to"]) if data.get("date_to") is not None else None,
        )

    @property
    def market_tz(self) -> str:
        return _market_tz_from_slot(self.slot_id)

    @property
    def run_label(self) -> str:
        return self.variant_code or self.experiment_code

    def comparison_label(self) -> str:
        filter_fragment = "__".join(_label_fragment(label) for label in self.baseline.filter_labels)
        return (
            f"{self.side}{_label_fragment(self.baseline.entry_clock_local)}_"
            f"{filter_fragment}_tp{self.baseline.tp_pips:g}_sl{self.baseline.sl_pips:g}_"
            f"fx{_label_fragment(self.baseline.forced_exit_clock_local)}"
        )

    def to_strategy_setting(
        self,
        *,
        pre_range_threshold: float | None = None,
        dynamic_filter_threshold: float | None = None,
    ) -> StrategySetting:
        return StrategySetting(
            setting_id=f"{self.slot_id}_{self.side}_{self.run_label}_tick_replay",
            slot_id=self.slot_id,
            side=self.side,  # type: ignore[arg-type]
            market_tz=self.market_tz,  # type: ignore[arg-type]
            entry_clock_local=self.baseline.entry_clock_local,
            forced_exit_clock_local=self.baseline.forced_exit_clock_local,
            tp_pips=self.baseline.tp_pips,
            sl_pips=self.baseline.sl_pips,
            filter_labels=self.baseline.filter_labels,
            exclude_windows=self.baseline.exclude_windows,
            pre_range_threshold=pre_range_threshold,
            dynamic_filter_threshold=dynamic_filter_threshold,
            notes=self.notes,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class E005E008Params:
    experiment_code: str
    variant_code: str | None
    slot_id: str
    side: str
    baseline: BaselineSettingInput
    pass_stability_gate: bool
    selected_experiments: tuple[str, ...]
    slippage_values: tuple[float, ...]
    entry_delay_values: tuple[int, ...]
    target_maintenance_margin_candidates: tuple[float, ...]
    kill_switch_dd_pct: float
    initial_capital_jpy: float = 100_000.0
    slippage_mode: str = "none"
    fixed_slippage_pips: float = 0.0
    entry_delay_seconds: int = 0
    notes: str | None = None
    date_from: str | None = None
    date_to: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "E005E008Params":
        experiment_code = str(data["experiment_code"])
        if experiment_code != "E005-E008":
            raise ValueError(f"Unsupported experiment_code for E005-E008 runner: {experiment_code}")
        selected_experiments = tuple(str(value).upper() for value in data.get("selected_experiments", ["E005", "E006", "E007", "E008"]))
        if not selected_experiments:
            raise ValueError("selected_experiments must not be empty")
        unsupported = [value for value in selected_experiments if value not in {"E005", "E006", "E007", "E008"}]
        if unsupported:
            raise ValueError(f"Unsupported selected_experiments: {unsupported}")
        slippage_values = tuple(float(value) for value in data.get("slippage_values", []))
        entry_delay_values = tuple(int(value) for value in data.get("entry_delay_values", []))
        raw_margin_candidates = data.get("target_maintenance_margin_candidates")
        if raw_margin_candidates is None:
            legacy_risk_fractions = tuple(float(value) for value in data.get("risk_fractions", []))
            sl_pips = float(dict(data["baseline"])["sl_pips"])
            # Legacy compatibility only: convert old risk_fraction grids to
            # target maintenance margin using the same USDJPY=150 approximation
            # as pips_year_rate_pct_at_150usd. New params must use
            # target_maintenance_margin_candidates directly.
            raw_margin_candidates = [
                25.0 * sl_pips / (risk_fraction * 150.0)
                for risk_fraction in legacy_risk_fractions
                if risk_fraction > 0.0
            ]
        target_maintenance_margin_candidates = tuple(sorted(float(value) for value in raw_margin_candidates))
        if not slippage_values:
            raise ValueError("slippage_values must not be empty")
        if not entry_delay_values:
            raise ValueError("entry_delay_values must not be empty")
        if not target_maintenance_margin_candidates:
            raise ValueError("target_maintenance_margin_candidates must not be empty")
        return cls(
            experiment_code=experiment_code,
            variant_code=str(data["variant_code"]) if data.get("variant_code") is not None else None,
            slot_id=str(data["slot_id"]),
            side=str(data["side"]),
            baseline=BaselineSettingInput.from_dict(dict(data["baseline"])),
            pass_stability_gate=bool(data["pass_stability_gate"]),
            selected_experiments=selected_experiments,
            slippage_values=slippage_values,
            entry_delay_values=entry_delay_values,
            target_maintenance_margin_candidates=target_maintenance_margin_candidates,
            kill_switch_dd_pct=float(data["kill_switch_dd_pct"]),
            initial_capital_jpy=float(data.get("initial_capital_jpy", 100_000.0)),
            slippage_mode=str(data.get("slippage_mode", "none")),
            fixed_slippage_pips=float(data.get("fixed_slippage_pips", 0.0)),
            entry_delay_seconds=int(data.get("entry_delay_seconds", 0)),
            notes=str(data["notes"]) if data.get("notes") is not None else None,
            date_from=str(data["date_from"]) if data.get("date_from") is not None else None,
            date_to=str(data["date_to"]) if data.get("date_to") is not None else None,
        )

    def to_e004_params(self) -> E004Params:
        return E004Params(
            experiment_code="E004",
            variant_code=self.variant_code,
            slot_id=self.slot_id,
            side=self.side,
            baseline=self.baseline,
            pass_stability_gate=self.pass_stability_gate,
            slippage_mode=self.slippage_mode,
            fixed_slippage_pips=self.fixed_slippage_pips,
            entry_delay_seconds=self.entry_delay_seconds,
            notes=self.notes,
            date_from=self.date_from,
            date_to=self.date_to,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_e001_params(path: str | Path) -> E001Params:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("E001 params must be a JSON object")
    return E001Params.from_dict(payload)


def load_e002_params(path: str | Path) -> E002Params:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("E002 params must be a JSON object")
    return E002Params.from_dict(payload)


def load_e003_params(path: str | Path) -> E003Params:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("E003 params must be a JSON object")
    return E003Params.from_dict(payload)


def load_e004_params(path: str | Path) -> E004Params:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("E004 params must be a JSON object")
    return E004Params.from_dict(payload)


def load_e005_e008_params(path: str | Path) -> E005E008Params:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("E005-E008 params must be a JSON object")
    return E005E008Params.from_dict(payload)
