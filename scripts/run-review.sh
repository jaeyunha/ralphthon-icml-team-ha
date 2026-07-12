#!/bin/bash
set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel)
FIXTURE_ONLY=0
MANIFEST=""
ARM_ID=""
WORKSPACE=""
OUTPUT=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --fixture-only) FIXTURE_ONLY=1; shift ;;
    --manifest) MANIFEST="${2:?--manifest requires a path}"; shift 2 ;;
    --arm-id) ARM_ID="${2:?--arm-id requires a value}"; shift 2 ;;
    --workspace) WORKSPACE="${2:?--workspace requires a path}"; shift 2 ;;
    --output) OUTPUT="${2:?--output requires a path}"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 64 ;;
  esac
done

if [ "$FIXTURE_ONLY" -ne 1 ]; then
  echo "Stage A disables paper-review model generation; only --fixture-only preparation is available." >&2
  exit 78
fi
if [ -z "$MANIFEST" ] || [ -z "$ARM_ID" ] || [ -z "$WORKSPACE" ] || [ -z "$OUTPUT" ]; then
  echo "usage: scripts/run-review.sh --fixture-only --manifest PATH --arm-id ID --workspace PATH --output PATH" >&2
  exit 64
fi

exec uv run python "$REPO_ROOT/engine/benchmark/coordinator.py" \
  --repo-root "$REPO_ROOT" prepare-review-fixture \
  --manifest "$MANIFEST" --arm-id "$ARM_ID" --workspace "$WORKSPACE" --output "$OUTPUT"
