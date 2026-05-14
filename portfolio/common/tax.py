from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from typing import Any

import pandas as pd


@dataclass
class ExternalLossOffset:
    amount_jpy: float
    expires_on: date | None = None


def parse_external_loss_offsets(raw: str | None) -> list[ExternalLossOffset]:
    if not raw:
        return []
    loaded: Any = json.loads(raw)
    if isinstance(loaded, dict):
        loaded = [loaded]
    offsets: list[ExternalLossOffset] = []
    for item in loaded:
        expires = item.get("expires_on")
        offsets.append(
            ExternalLossOffset(
                amount_jpy=float(item.get("amount_jpy", 0.0)),
                expires_on=pd.to_datetime(expires).date() if expires else None,
            )
        )
    return offsets


def month_day_date(year: int, month_day: str) -> date:
    month, day = (int(part) for part in month_day.split("-", 1))
    return date(year, month, day)
