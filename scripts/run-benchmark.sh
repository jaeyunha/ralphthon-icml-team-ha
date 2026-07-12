#!/bin/bash
set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel)
FIXTURE_ONLY=0
MANIFEST=""
OUTPUT=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --fixture-only) FIXTURE_ONLY=1; shift ;;
    --manifest) MANIFEST="${2:?--manifest requires a path}"; shift 2 ;;
    --output) OUTPUT="${2:?--output requires a path}"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 64 ;;
  esac
done

if [ "$FIXTURE_ONLY" -ne 1 ]; then
  echo "Stage A disables the seven-paper campaign, model generation, outcome reveal, and scoring." >&2
  exit 78
fi
if [ -z "$MANIFEST" ] || [ -z "$OUTPUT" ]; then
  echo "usage: scripts/run-benchmark.sh --fixture-only --manifest PATH --output PATH" >&2
  exit 64
fi

exec uv run python "$REPO_ROOT/engine/benchmark/coordinator.py" \
  --repo-root "$REPO_ROOT" prepare-benchmark-fixture \
  --manifest "$MANIFEST" --output "$OUTPUT"
