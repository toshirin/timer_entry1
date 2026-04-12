from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def to_attr(value: Any) -> dict[str, Any]:
    if value is None:
        return {"NULL": True}
    if isinstance(value, bool):
        return {"BOOL": value}
    if isinstance(value, int):
        return {"N": str(value)}
    if isinstance(value, float):
        return {"N": str(value)}
    if isinstance(value, str):
        return {"S": value}
    if isinstance(value, list):
        return {"L": [to_attr(item) for item in value]}
    if isinstance(value, dict):
        return {"M": {key: to_attr(item) for key, item in value.items()}}
    raise TypeError(f"Unsupported value type: {type(value)!r}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: json_to_dynamodb_item.py <json-file>")

    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("top-level JSON must be an object")

    now_iso = datetime.now(timezone.utc).isoformat()
    existing_created_at = os.environ.get("TIMER_ENTRY_RUNTIME_CREATED_AT")
    if existing_created_at:
        payload["created_at"] = existing_created_at
    else:
        payload.setdefault("created_at", now_iso)
    payload["updated_at"] = now_iso

    print(json.dumps({key: to_attr(value) for key, value in payload.items()}, ensure_ascii=True))


if __name__ == "__main__":
    main()
