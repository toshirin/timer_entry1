from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SAMPLE_MONTH_DAYS: tuple[tuple[int, int], ...] = tuple(
    (month, day)
    for month in range(1, 13)
    for day in (1, 15)
)


@dataclass(frozen=True)
class ScheduleExpression:
    expression: str
    pairs: tuple[tuple[int, int], ...]
    invocation_pairs: tuple[tuple[int, int], ...]
    extra_pairs: tuple[tuple[int, int], ...]


def _clock_parts(clock_hhmm: str) -> tuple[int, int]:
    parts = clock_hhmm.split(":")
    if len(parts) != 2:
        raise ValueError(f"clock must be HH:MM format: {clock_hhmm}")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"clock out of range: {clock_hhmm}")
    return hour, minute


def _utc_pairs_for_local_clock(clock_hhmm: str, tz_name: str, years: range) -> set[tuple[int, int]]:
    hour, minute = _clock_parts(clock_hhmm)
    zone = ZoneInfo(tz_name)
    pairs: set[tuple[int, int]] = set()
    for year in years:
        for month, day in SAMPLE_MONTH_DAYS:
            local_dt = datetime(year, month, day, hour, minute, tzinfo=zone)
            utc_dt = local_dt.astimezone(timezone.utc)
            pairs.add((utc_dt.hour, utc_dt.minute))
    return pairs


def _format_field(values: list[int]) -> str:
    if len(values) == 24 and values == list(range(24)):
        return "*"
    return ",".join(str(value) for value in values)


def _to_expression(pairs: set[tuple[int, int]]) -> ScheduleExpression:
    if not pairs:
        raise ValueError("no schedule pairs found")
    hours = sorted({hour for hour, _ in pairs})
    invocation_pairs = {(hour, minute) for hour in hours for minute in range(0, 60, 5)}
    extra_pairs = tuple(sorted(invocation_pairs - pairs))
    expression = f"cron(*/5 {_format_field(hours)} * * ? *)"
    return ScheduleExpression(
        expression=expression,
        pairs=tuple(sorted(pairs)),
        invocation_pairs=tuple(sorted(invocation_pairs)),
        extra_pairs=extra_pairs,
    )


def _load_configs(config_dir: Path, *, enabled_only: bool) -> list[dict[str, Any]]:
    configs: list[dict[str, Any]] = []
    for path in sorted(config_dir.rglob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"config must be a JSON object: {path}")
        if enabled_only and not bool(payload.get("enabled", False)):
            continue
        payload["_source_path"] = str(path)
        configs.append(payload)
    return configs


def _collect_pairs(configs: list[dict[str, Any]], *, clock_key: str, years: range) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    for config in configs:
        clock = str(config[clock_key])
        tz_name = str(config["market_tz"])
        pairs.update(_utc_pairs_for_local_clock(clock, tz_name, years))
    return pairs


def _pair_text(pairs: tuple[tuple[int, int], ...]) -> str:
    return ",".join(f"{hour:02d}:{minute:02d}" for hour, minute in pairs) or "-"


def _render_env(entry: ScheduleExpression, exit_: ScheduleExpression) -> str:
    lines = [
        f"ENTRY_SCHEDULE_EXPRESSION='{entry.expression}'",
        f"EXIT_SCHEDULE_EXPRESSION='{exit_.expression}'",
        f"# entry_utc_pairs={_pair_text(entry.pairs)}",
        f"# exit_utc_pairs={_pair_text(exit_.pairs)}",
    ]
    return "\n".join(lines)


def _render_json(entry: ScheduleExpression, exit_: ScheduleExpression) -> str:
    return json.dumps(
        {
            "entry_schedule_expression": entry.expression,
            "exit_schedule_expression": exit_.expression,
            "entry_utc_pairs": [f"{hour:02d}:{minute:02d}" for hour, minute in entry.pairs],
            "exit_utc_pairs": [f"{hour:02d}:{minute:02d}" for hour, minute in exit_.pairs],
            "entry_invocation_utc_pairs": [f"{hour:02d}:{minute:02d}" for hour, minute in entry.invocation_pairs],
            "exit_invocation_utc_pairs": [f"{hour:02d}:{minute:02d}" for hour, minute in exit_.invocation_pairs],
            "entry_extra_invocation_utc_pairs": [f"{hour:02d}:{minute:02d}" for hour, minute in entry.extra_pairs],
            "exit_extra_invocation_utc_pairs": [f"{hour:02d}:{minute:02d}" for hour, minute in exit_.extra_pairs],
        },
        ensure_ascii=False,
        indent=2,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate EventBridge cron expressions from runtime setting configs.")
    parser.add_argument("--config-dir", default="runtime/config")
    parser.add_argument("--enabled-only", action="store_true")
    parser.add_argument("--start-year", type=int, default=datetime.now(timezone.utc).year)
    parser.add_argument("--years", type=int, default=2)
    parser.add_argument("--format", choices=("env", "json"), default="env")
    args = parser.parse_args(argv)

    if args.years <= 0:
        raise ValueError("--years must be greater than zero")
    years = range(args.start_year, args.start_year + args.years)
    configs = _load_configs(Path(args.config_dir), enabled_only=args.enabled_only)
    if not configs:
        raise ValueError(f"no config JSON files found under {args.config_dir}")

    entry = _to_expression(_collect_pairs(configs, clock_key="entry_clock_local", years=years))
    exit_ = _to_expression(_collect_pairs(configs, clock_key="forced_exit_clock_local", years=years))

    if args.format == "json":
        print(_render_json(entry, exit_))
    else:
        print(_render_env(entry, exit_))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
