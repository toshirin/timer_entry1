from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

from .features import FeatureComputationResult


FilterFamily = Literal[
    "all",
    "pre_open_slope",
    "shape_balance",
    "pre_range_regime",
    "trend_ratio",
]


@dataclass(frozen=True)
class RuntimeFilterSpec:
    # runtime 側でそのまま consume しやすい spec 形式。
    # filter_type / operator / mode / threshold の粒度に揃える。
    filter_type: str
    operator: str | None = None
    mode: str | None = None
    threshold: float | None = None
    lookback_start_min: int = 55
    lookback_end_min: int = 5
    left_start_min: int = 55
    left_end_min: int = 30
    right_start_min: int = 30
    right_end_min: int = 5

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "filter_type": self.filter_type,
        }
        if self.operator is not None:
            data["operator"] = self.operator
        if self.mode is not None:
            data["mode"] = self.mode
        if self.threshold is not None:
            data["threshold"] = self.threshold
        if self.filter_type == "pre_open_slope":
            data["lookback_start_min"] = self.lookback_start_min
            data["lookback_end_min"] = self.lookback_end_min
        elif self.filter_type == "shape_balance":
            data["left_start_min"] = self.left_start_min
            data["left_end_min"] = self.left_end_min
            data["right_start_min"] = self.right_start_min
            data["right_end_min"] = self.right_end_min
        elif self.filter_type in {"pre_range_regime", "trend_ratio"}:
            data["lookback_start_min"] = self.lookback_start_min
            data["lookback_end_min"] = self.lookback_end_min
        return data


@dataclass(frozen=True)
class CanonicalFilter:
    # scan / qualify / runtime をまたぐ canonical 定義。
    # label を主語にしつつ、runtime へは RuntimeFilterSpec に落とせるようにする。
    label: str
    family: FilterFamily


SCAN_FILTERS: tuple[CanonicalFilter, ...] = (
    CanonicalFilter(label="all", family="all"),
    CanonicalFilter(label="ge0", family="pre_open_slope"),
    CanonicalFilter(label="le0", family="pre_open_slope"),
    CanonicalFilter(label="left_stronger", family="shape_balance"),
    CanonicalFilter(label="right_stronger", family="shape_balance"),
    CanonicalFilter(label="same_sign", family="shape_balance"),
    CanonicalFilter(label="opposite_sign", family="shape_balance"),
    CanonicalFilter(label="vol_ge_med", family="pre_range_regime"),
    CanonicalFilter(label="vol_lt_med", family="pre_range_regime"),
    CanonicalFilter(label="trend_ge_0_5", family="trend_ratio"),
    CanonicalFilter(label="range_lt_0_3", family="trend_ratio"),
)


SCAN_FILTER_MAP: dict[str, CanonicalFilter] = {item.label: item for item in SCAN_FILTERS}
_SLOPE_LABEL_RE = re.compile(r"^(ge|le)(-?\d+(?:[._]\d+)?)$")
_VOL_PERCENTILE_LABEL_RE = re.compile(r"^vol_(ge|lt)_p(100|[1-9]?\d)$")
_RIGHT_DOMINANCE_LABEL_RE = re.compile(r"^right_dom_ge(-?\d+(?:[._]\d+)?)$")


def canonical_filter_labels() -> list[str]:
    return [item.label for item in SCAN_FILTERS]


def get_canonical_filter(label: str) -> CanonicalFilter:
    if label not in SCAN_FILTER_MAP:
        raise ValueError(f"Unsupported canonical filter label: {label}")
    return SCAN_FILTER_MAP[label]


def parse_slope_filter_label(label: str) -> tuple[str, float] | None:
    match = _SLOPE_LABEL_RE.fullmatch(label)
    if match is None:
        return None
    operator, raw_threshold = match.groups()
    threshold = float(raw_threshold.replace("_", "."))
    return operator, threshold


def parse_volatility_filter_label(label: str) -> tuple[str, str | int] | None:
    if label == "vol_ge_med":
        return "ge", "med"
    if label == "vol_lt_med":
        return "lt", "med"
    match = _VOL_PERCENTILE_LABEL_RE.fullmatch(label)
    if match is None:
        return None
    operator, percentile_text = match.groups()
    return operator, int(percentile_text)


def parse_right_dominance_filter_label(label: str) -> tuple[str, float] | None:
    match = _RIGHT_DOMINANCE_LABEL_RE.fullmatch(label)
    if match is None:
        return None
    return "ge", float(match.group(1).replace("_", "."))


def get_filter_family(label: str) -> FilterFamily:
    canonical = SCAN_FILTER_MAP.get(label)
    if canonical is not None:
        return canonical.family
    if parse_slope_filter_label(label) is not None:
        return "pre_open_slope"
    if parse_volatility_filter_label(label) is not None:
        return "pre_range_regime"
    if parse_right_dominance_filter_label(label) is not None:
        return "shape_balance"
    raise ValueError(f"Unsupported filter label: {label}")


def evaluate_canonical_filter(
    label: str,
    features: FeatureComputationResult,
    *,
    pre_range_median: float | None = None,
    pre_range_threshold: float | None = None,
    dynamic_threshold: float | None = None,
) -> bool:
    # scan / qualify の DataFrame 側で使う簡易評価器。
    if not features.feature_available:
        return False

    resolved_pre_range_threshold = pre_range_threshold
    if resolved_pre_range_threshold is None:
        resolved_pre_range_threshold = pre_range_median

    if label == "all":
        return True
    slope_spec = parse_slope_filter_label(label)
    if slope_spec is not None:
        operator, threshold = slope_spec
        if operator == "ge":
            return features.pre_open_slope_pips >= threshold
        return features.pre_open_slope_pips <= threshold
    if label == "left_stronger":
        return features.left_stronger
    if label == "right_stronger":
        return features.right_stronger
    if label == "same_sign":
        return features.same_sign
    if label == "opposite_sign":
        return features.opposite_sign
    vol_spec = parse_volatility_filter_label(label)
    if vol_spec is not None:
        if resolved_pre_range_threshold is None:
            raise ValueError(f"pre_range_threshold is required for {label}")
        operator, _ = vol_spec
        if operator == "ge":
            return features.pre_range_pips >= resolved_pre_range_threshold
        return features.pre_range_pips < resolved_pre_range_threshold
    right_dom_spec = parse_right_dominance_filter_label(label)
    if right_dom_spec is not None:
        if dynamic_threshold is None:
            raise ValueError(f"dynamic_threshold is required for {label}")
        return features.right_strength_balance_pips >= dynamic_threshold
    if label == "trend_ge_0_5":
        return features.trend_ratio == features.trend_ratio and features.trend_ratio >= 0.5
    if label == "range_lt_0_3":
        return features.trend_ratio == features.trend_ratio and features.trend_ratio < 0.3
    raise ValueError(f"Unsupported canonical filter label: {label}")


def to_runtime_filter_spec(
    label: str,
    *,
    pre_range_threshold: float | None = None,
    dynamic_threshold: float | None = None,
) -> RuntimeFilterSpec | None:
    # runtime 側には family ベースの spec へ変換して渡す。
    # `all` は filter 無し運用と同義なので None を返す。
    if label == "all":
        return None
    slope_spec = parse_slope_filter_label(label)
    if slope_spec is not None:
        operator, threshold = slope_spec
        return RuntimeFilterSpec(filter_type="pre_open_slope", operator=operator, threshold=threshold)
    if label == "left_stronger":
        return RuntimeFilterSpec(filter_type="shape_balance", mode="left_stronger")
    if label == "right_stronger":
        return RuntimeFilterSpec(filter_type="shape_balance", mode="right_stronger")
    if label == "same_sign":
        return RuntimeFilterSpec(filter_type="shape_balance", mode="same_sign")
    if label == "opposite_sign":
        return RuntimeFilterSpec(filter_type="shape_balance", mode="opposite_sign")
    vol_spec = parse_volatility_filter_label(label)
    if vol_spec is not None:
        if pre_range_threshold is None:
            raise ValueError(f"pre_range_threshold is required for {label}")
        operator, _ = vol_spec
        return RuntimeFilterSpec(filter_type="pre_range_regime", operator=operator, threshold=float(pre_range_threshold))
    right_dom_spec = parse_right_dominance_filter_label(label)
    if right_dom_spec is not None:
        if dynamic_threshold is None:
            raise ValueError(f"dynamic_threshold is required for {label}")
        return RuntimeFilterSpec(
            filter_type="shape_balance",
            operator="ge",
            mode="right_strength_balance",
            threshold=float(dynamic_threshold),
        )
    if label == "trend_ge_0_5":
        return RuntimeFilterSpec(filter_type="trend_ratio", operator="ge", threshold=0.5)
    if label == "range_lt_0_3":
        return RuntimeFilterSpec(filter_type="trend_ratio", operator="lt", threshold=0.3)
    raise ValueError(f"Unsupported canonical filter label: {label}")


def runtime_filter_dicts(
    labels: list[str],
    *,
    pre_range_threshold: float | None = None,
    dynamic_threshold: float | None = None,
) -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    for label in labels:
        spec = to_runtime_filter_spec(
            label,
            pre_range_threshold=pre_range_threshold,
            dynamic_threshold=dynamic_threshold,
        )
        if spec is not None:
            specs.append(spec.to_dict())
    return specs


__all__ = [
    "CanonicalFilter",
    "FilterFamily",
    "RuntimeFilterSpec",
    "SCAN_FILTERS",
    "SCAN_FILTER_MAP",
    "canonical_filter_labels",
    "evaluate_canonical_filter",
    "get_filter_family",
    "get_canonical_filter",
    "parse_slope_filter_label",
    "parse_right_dominance_filter_label",
    "parse_volatility_filter_label",
    "runtime_filter_dicts",
    "to_runtime_filter_spec",
]
