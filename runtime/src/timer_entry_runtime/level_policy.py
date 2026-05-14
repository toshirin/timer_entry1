from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal


POLICY_NAME = "unit_level_policy"
POLICY_VERSION = "2026-04-17"
MIN_LEVEL = 0
MAX_LEVEL = 7
LEVEL0_FIXED_UNITS = 10
WATCH_LABEL = "watch"
MONTHLY_SOURCE = "monthly"
UNIT_BASIS_MONTH_END = "month_end_latest_equity_runtime_compute_units"

LevelMode = Literal["fixed_units", "size_scale_pct"]
Decision = Literal["promote", "demote", "keep", "force_level0_watch"]


@dataclass(frozen=True)
class UnitLevelSpec:
    level: int
    mode: LevelMode
    fixed_units: int | None = None
    size_scale_pct: float | None = None


@dataclass(frozen=True)
class UnitLevelDecision:
    source: str
    current_level: int
    next_level: int
    decision: Decision
    decision_reason: str
    current_units: int | None = None
    threshold_jpy: float | None = None
    cum_jpy_month: float | None = None
    unit_basis: str | None = None
    policy_name: str = POLICY_NAME
    policy_version: str = POLICY_VERSION

    @property
    def changed(self) -> bool:
        return self.next_level != self.current_level


DEFAULT_LEVELS: tuple[UnitLevelSpec, ...] = (
    UnitLevelSpec(level=0, mode="fixed_units", fixed_units=LEVEL0_FIXED_UNITS),
    UnitLevelSpec(level=1, mode="size_scale_pct", size_scale_pct=0.1),
    UnitLevelSpec(level=2, mode="size_scale_pct", size_scale_pct=0.3),
    UnitLevelSpec(level=3, mode="size_scale_pct", size_scale_pct=1.0),
    UnitLevelSpec(level=4, mode="size_scale_pct", size_scale_pct=3.0),
    UnitLevelSpec(level=5, mode="size_scale_pct", size_scale_pct=10.0),
    UnitLevelSpec(level=6, mode="size_scale_pct", size_scale_pct=30.0),
    UnitLevelSpec(level=7, mode="size_scale_pct", size_scale_pct=100.0),
)


def level_spec(level: int, levels: Iterable[UnitLevelSpec] = DEFAULT_LEVELS) -> UnitLevelSpec:
    _validate_level(level)
    for spec in levels:
        if spec.level == level:
            return spec
    raise ValueError(f"unit level spec is not defined: {level}")


def level_sizing_fields(level: int, levels: Iterable[UnitLevelSpec] = DEFAULT_LEVELS) -> dict[str, int | float | None]:
    spec = level_spec(level, levels)
    if spec.mode == "fixed_units":
        if spec.fixed_units is None or spec.fixed_units <= 0:
            raise ValueError(f"fixed_units must be positive for level {level}")
        return {"fixed_units": spec.fixed_units, "size_scale_pct": None}
    if spec.size_scale_pct is None or spec.size_scale_pct <= 0:
        raise ValueError(f"size_scale_pct must be positive for level {level}")
    return {"fixed_units": None, "size_scale_pct": spec.size_scale_pct}


def infer_level_from_sizing(
    *,
    unit_level: int | None,
    fixed_units: int | None,
    size_scale_pct: float | None,
    levels: Iterable[UnitLevelSpec] = DEFAULT_LEVELS,
) -> int:
    if unit_level is not None:
        _validate_level(unit_level)
        return unit_level

    if fixed_units is not None:
        for spec in levels:
            if spec.mode == "fixed_units" and spec.fixed_units == fixed_units:
                return spec.level
        raise ValueError(f"unit level cannot be inferred from fixed_units: {fixed_units}")

    if size_scale_pct is not None:
        for spec in levels:
            if spec.mode == "size_scale_pct" and spec.size_scale_pct == size_scale_pct:
                return spec.level
        raise ValueError(f"unit level cannot be inferred from size_scale_pct: {size_scale_pct}")

    raise ValueError("unit level cannot be inferred without unit_level, fixed_units, or size_scale_pct")


def threshold_jpy_for_units(current_units: int) -> float:
    _validate_units(current_units)
    return 0.1 * current_units


def decide_monthly_level(
    *,
    current_level: int,
    current_units: int,
    cum_jpy_month: float,
    labels: Iterable[str] = (),
    unit_basis: str = UNIT_BASIS_MONTH_END,
) -> UnitLevelDecision:
    _validate_level(current_level)
    threshold_jpy = threshold_jpy_for_units(current_units)

    if _has_watch_label(labels):
        return UnitLevelDecision(
            source=MONTHLY_SOURCE,
            current_level=current_level,
            next_level=MIN_LEVEL,
            decision="force_level0_watch",
            decision_reason="watch_label",
            current_units=current_units,
            threshold_jpy=threshold_jpy,
            cum_jpy_month=float(cum_jpy_month),
            unit_basis=unit_basis,
        )

    if cum_jpy_month > threshold_jpy:
        if current_level >= MAX_LEVEL:
            return UnitLevelDecision(
                source=MONTHLY_SOURCE,
                current_level=current_level,
                next_level=MAX_LEVEL,
                decision="keep",
                decision_reason="already_at_max_level_profit_above_threshold",
                current_units=current_units,
                threshold_jpy=threshold_jpy,
                cum_jpy_month=float(cum_jpy_month),
                unit_basis=unit_basis,
            )
        return UnitLevelDecision(
            source=MONTHLY_SOURCE,
            current_level=current_level,
            next_level=current_level + 1,
            decision="promote",
            decision_reason="monthly_profit_above_threshold",
            current_units=current_units,
            threshold_jpy=threshold_jpy,
            cum_jpy_month=float(cum_jpy_month),
            unit_basis=unit_basis,
        )

    if cum_jpy_month < -threshold_jpy:
        if current_level <= MIN_LEVEL:
            return UnitLevelDecision(
                source=MONTHLY_SOURCE,
                current_level=current_level,
                next_level=MIN_LEVEL,
                decision="keep",
                decision_reason="already_at_min_level_loss_below_threshold",
                current_units=current_units,
                threshold_jpy=threshold_jpy,
                cum_jpy_month=float(cum_jpy_month),
                unit_basis=unit_basis,
            )
        return UnitLevelDecision(
            source=MONTHLY_SOURCE,
            current_level=current_level,
            next_level=current_level - 1,
            decision="demote",
            decision_reason="monthly_loss_below_threshold",
            current_units=current_units,
            threshold_jpy=threshold_jpy,
            cum_jpy_month=float(cum_jpy_month),
            unit_basis=unit_basis,
        )

    return UnitLevelDecision(
        source=MONTHLY_SOURCE,
        current_level=current_level,
        next_level=current_level,
        decision="keep",
        decision_reason="monthly_pnl_within_band",
        current_units=current_units,
        threshold_jpy=threshold_jpy,
        cum_jpy_month=float(cum_jpy_month),
        unit_basis=unit_basis,
    )


def decide_emergency_demotion(
    *,
    current_level: int,
    source: str,
    decision_reason: str,
) -> UnitLevelDecision:
    _validate_level(current_level)
    if not source:
        raise ValueError("source is required")
    if not decision_reason:
        raise ValueError("decision_reason is required")

    if current_level <= MIN_LEVEL:
        return UnitLevelDecision(
            source=source,
            current_level=current_level,
            next_level=MIN_LEVEL,
            decision="keep",
            decision_reason=f"already_at_min_level_{decision_reason}",
        )
    return UnitLevelDecision(
        source=source,
        current_level=current_level,
        next_level=current_level - 1,
        decision="demote",
        decision_reason=decision_reason,
    )


def _has_watch_label(labels: Iterable[str]) -> bool:
    return any(str(label).strip().lower() == WATCH_LABEL for label in labels)


def _validate_level(level: int) -> None:
    if level < MIN_LEVEL or level > MAX_LEVEL:
        raise ValueError(f"unit level must be between {MIN_LEVEL} and {MAX_LEVEL}: {level}")


def _validate_units(current_units: int) -> None:
    if current_units <= 0:
        raise ValueError(f"current_units must be greater than zero: {current_units}")
