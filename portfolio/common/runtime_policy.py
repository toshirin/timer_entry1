from __future__ import annotations

from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[2]
RUNTIME_SRC = ROOT_DIR / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from timer_entry_runtime.level_policy import (  # noqa: E402
    LEVEL0_FIXED_UNITS,
    MAX_LEVEL,
    MIN_LEVEL,
    UNIT_BASIS_MONTH_END,
    decide_monthly_level,
    level_sizing_fields,
    threshold_jpy_for_units,
)
