#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$ROOT_DIR/.." && pwd)"
BUILD_DIR="$ROOT_DIR/.build"
DIST_DIR="$ROOT_DIR/dist"
SRC_DIR="$ROOT_DIR/src"
CORE_SRC_DIR="$REPO_DIR/src/timer_entry"
REQ_FILE="$ROOT_DIR/requirements.txt"
CORE_RUNTIME_FILES=(
  "direction.py"
  "filters.py"
  "schemas.py"
  "time_utils.py"
)

has_runtime_requirements() {
  [[ -f "$REQ_FILE" ]] && grep -Eq '^[[:space:]]*[^#[:space:]]' "$REQ_FILE"
}

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR"

build_zip() {
  local output_name="$1"
  local staging_dir="$BUILD_DIR/$output_name"

  rm -rf "$staging_dir"
  mkdir -p "$staging_dir/timer_entry"
  cp -R "$SRC_DIR"/. "$staging_dir"/
  : >"$staging_dir/timer_entry/__init__.py"
  for core_file in "${CORE_RUNTIME_FILES[@]}"; do
    cp "$CORE_SRC_DIR/$core_file" "$staging_dir/timer_entry/$core_file"
  done

  if has_runtime_requirements; then
    python3 -m pip install \
      --no-cache-dir \
      --platform manylinux2014_x86_64 \
      --implementation cp \
      --python-version 3.12 \
      --only-binary=:all: \
      --target "$staging_dir" \
      -r "$REQ_FILE"
  fi

  python3 - "$staging_dir" "$DIST_DIR/$output_name.zip" <<'PY'
import pathlib
import sys
import zipfile

staging_dir = pathlib.Path(sys.argv[1])
zip_path = pathlib.Path(sys.argv[2])

with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for path in sorted(staging_dir.rglob("*")):
        if path.is_file():
            zf.write(path, path.relative_to(staging_dir))
PY
}

rm -f "$DIST_DIR/entry_handler.zip" "$DIST_DIR/forced_exit_handler.zip"
build_zip "entry_handler"
build_zip "forced_exit_handler"

echo "Built artifacts:"
echo "  $DIST_DIR/entry_handler.zip"
echo "  $DIST_DIR/forced_exit_handler.zip"
