from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def emit_log(event_name: str, **fields: Any) -> None:
    payload = {
        "event_name": event_name,
        "logged_at_utc": datetime.now(timezone.utc).isoformat(),
        **fields,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))

