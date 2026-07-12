#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)

if [ -n "${PYTHON:-}" ]; then
  exec "$PYTHON" "$SCRIPT_DIR/watchdog_runtime.py" "$@"
fi
if command -v uv >/dev/null 2>&1 && [ -f "$REPO_ROOT/uv.lock" ]; then
  exec uv run --frozen python "$SCRIPT_DIR/watchdog_runtime.py" "$@"
fi
exec python3 "$SCRIPT_DIR/watchdog_runtime.py" "$@"
