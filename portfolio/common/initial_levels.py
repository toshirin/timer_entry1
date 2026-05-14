from __future__ import annotations

import pandas as pd

from .unit_level import MAX_LEVEL, MIN_LEVEL


def add_initial_level_args(parser) -> None:
    parser.add_argument("--initial-level", type=int, default=None)
    parser.add_argument(
        "--initial-level-setting",
        action="append",
        default=[],
        metavar="SETTING_OR_SLOT=LEVEL",
        help="Override one setting initial level. Key may be setting_id or unique slot_id. Repeatable.",
    )


def validate_level(level: int) -> int:
    value = int(level)
    if value < MIN_LEVEL or value > MAX_LEVEL:
        raise ValueError(f"initial level must be between {MIN_LEVEL} and {MAX_LEVEL}: {value}")
    return value


def parse_initial_level_overrides(values: list[str] | None) -> dict[str, int]:
    overrides: dict[str, int] = {}
    for raw in values or []:
        if "=" not in raw:
            raise ValueError(f"--initial-level-setting must be SETTING_OR_SLOT=LEVEL: {raw}")
        key, level_raw = raw.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"--initial-level-setting key is empty: {raw}")
        overrides[key] = validate_level(int(level_raw.strip()))
    return overrides


def apply_initial_levels(
    settings: pd.DataFrame,
    *,
    global_initial_level: int | None,
    setting_overrides: list[str] | None,
) -> pd.DataFrame:
    out = settings.copy()
    out["initial_level_source"] = "runtime_config"
    if global_initial_level is not None:
        out["initial_level"] = validate_level(global_initial_level)
        out["initial_level_source"] = "cli_global"

    overrides = parse_initial_level_overrides(setting_overrides)
    for key, level in overrides.items():
        setting_mask = out["setting_id"].astype(str).eq(key)
        if setting_mask.any():
            mask = setting_mask
        else:
            slot_mask = out["slot_id"].astype(str).eq(key)
            if int(slot_mask.sum()) == 1:
                mask = slot_mask
            elif int(slot_mask.sum()) > 1:
                matches = sorted(out.loc[slot_mask, "setting_id"].astype(str).tolist())
                raise ValueError(f"--initial-level-setting {key} matches multiple settings: {matches}")
            else:
                raise ValueError(f"--initial-level-setting unknown setting_id or slot_id: {key}")
        out.loc[mask, "initial_level"] = level
        out.loc[mask, "initial_level_source"] = f"cli:{key}"
    return out
