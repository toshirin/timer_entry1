#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
JSON_PATH="${1:-}"
TABLE_NAME="${SETTING_CONFIG_TABLE_NAME:-timer-entry-runtime-setting-config}"
AWS_REGION_VALUE="${AWS_REGION:-${AWS_DEFAULT_REGION:-ap-northeast-1}}"

if [[ -z "$JSON_PATH" ]]; then
  echo "usage: $0 <setting-json-path>" >&2
  exit 1
fi

if [[ ! -f "$JSON_PATH" ]]; then
  echo "setting json not found: $JSON_PATH" >&2
  exit 1
fi

if ! command -v aws >/dev/null 2>&1; then
  echo "aws CLI is required" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi

SETTING_ID="$(python3 - <<'PY' "$JSON_PATH"
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    payload = json.load(fh)
print(payload["setting_id"])
PY
)"

EXISTING_CREATED_AT="$(
  aws dynamodb get-item \
    --region "$AWS_REGION_VALUE" \
    --table-name "$TABLE_NAME" \
    --key "{\"setting_id\":{\"S\":\"$SETTING_ID\"}}" \
    --projection-expression "created_at" \
    --query "Item.created_at.S" \
    --output text 2>/dev/null || true
)"

if [[ "$EXISTING_CREATED_AT" == "None" ]]; then
  EXISTING_CREATED_AT=""
fi

TMP_ITEM="$(mktemp /tmp/timer_entry_runtime_item.XXXXXX.json)"
trap 'rm -f "$TMP_ITEM"' EXIT

TIMER_ENTRY_RUNTIME_CREATED_AT="$EXISTING_CREATED_AT" \
  python3 "$ROOT_DIR/scripts/json_to_dynamodb_item.py" "$JSON_PATH" >"$TMP_ITEM"

aws dynamodb put-item \
  --region "$AWS_REGION_VALUE" \
  --table-name "$TABLE_NAME" \
  --item "file://$TMP_ITEM"

echo "Applied setting:"
echo "  table_name=$TABLE_NAME"
echo "  setting_id=$SETTING_ID"
if [[ -n "$EXISTING_CREATED_AT" ]]; then
  echo "  created_at_preserved=$EXISTING_CREATED_AT"
else
  echo "  created_at_preserved=<new>"
fi
