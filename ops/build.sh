#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/ops/dist"
BUILD_DIR="$DIST_DIR/daily_transaction_import"

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
cp -R "$ROOT_DIR/ops/src/timer_entry_ops" "$BUILD_DIR/timer_entry_ops"

mkdir -p "$DIST_DIR"
(
  cd "$BUILD_DIR"
  python3 -m zipfile -c "$DIST_DIR/daily_transaction_import.zip" timer_entry_ops
)

echo "built $DIST_DIR/daily_transaction_import.zip"
