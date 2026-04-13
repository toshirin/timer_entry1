#!/usr/bin/env bash
set -euo pipefail

SETTING_ID="${1:-}"
TABLE_NAME="${SETTING_CONFIG_TABLE_NAME:-timer-entry-runtime-setting-config}"
AWS_REGION_VALUE="${AWS_REGION:-${AWS_DEFAULT_REGION:-ap-northeast-1}}"

if [[ -z "$SETTING_ID" ]]; then
  echo "usage: $0 <setting_id>" >&2
  exit 1
fi

if ! command -v aws >/dev/null 2>&1; then
  echo "aws CLI is required" >&2
  exit 1
fi

aws dynamodb update-item \
  --region "$AWS_REGION_VALUE" \
  --table-name "$TABLE_NAME" \
  --key "{\"setting_id\":{\"S\":\"$SETTING_ID\"}}" \
  --update-expression "SET enabled = :false_value, updated_at = :updated_at" \
  --expression-attribute-values "{\":false_value\":{\"BOOL\":false},\":updated_at\":{\"S\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}}"

echo "Disabled setting:"
echo "  table_name=$TABLE_NAME"
echo "  setting_id=$SETTING_ID"
