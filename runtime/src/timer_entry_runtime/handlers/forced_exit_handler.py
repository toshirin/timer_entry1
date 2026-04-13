from __future__ import annotations

from typing import Any

from timer_entry_runtime.runtime import run_forced_exit_handler


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    return run_forced_exit_handler(event=event or {}, context=context)

