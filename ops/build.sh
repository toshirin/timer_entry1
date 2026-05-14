#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/ops/dist"
BUILD_ROOT="$DIST_DIR/.build"
OPS_SRC_DIR="$ROOT_DIR/ops/src/timer_entry_ops"
RUNTIME_SRC_DIR="$ROOT_DIR/runtime/src/timer_entry_runtime"
CORE_SRC_DIR="$ROOT_DIR/src/timer_entry"
CORE_RUNTIME_FILES=(
  "direction.py"
  "filters.py"
  "schemas.py"
  "time_utils.py"
)

rm -rf "$BUILD_ROOT"
mkdir -p "$BUILD_ROOT" "$DIST_DIR"

build_zip() {
  local output_name="$1"
  local include_runtime="$2"
  local build_dir="$BUILD_ROOT/$output_name"

  rm -rf "$build_dir"
  mkdir -p "$build_dir"
  cp -R "$OPS_SRC_DIR" "$build_dir/timer_entry_ops"
  if [[ "$include_runtime" == "yes" ]]; then
    cp -R "$RUNTIME_SRC_DIR" "$build_dir/timer_entry_runtime"
    mkdir -p "$build_dir/timer_entry"
    : >"$build_dir/timer_entry/__init__.py"
    for core_file in "${CORE_RUNTIME_FILES[@]}"; do
      cp "$CORE_SRC_DIR/$core_file" "$build_dir/timer_entry/$core_file"
    done
  fi
  (
    cd "$build_dir"
    if [[ "$include_runtime" == "yes" ]]; then
      python3 -m zipfile -c "$DIST_DIR/$output_name.zip" timer_entry_ops timer_entry_runtime timer_entry
    else
      python3 -m zipfile -c "$DIST_DIR/$output_name.zip" timer_entry_ops
    fi
  )
  echo "built $DIST_DIR/$output_name.zip"
}

build_zip "daily_transaction_import" "yes"
build_zip "monthly_unit_level_policy" "yes"
