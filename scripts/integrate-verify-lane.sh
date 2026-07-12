#!/bin/bash
# INTEGRATE: verify a lane merge candidate from a CLEAN checkout of the
# merge result (main + lane branch) in a throwaway worktree, then report.
# Does NOT touch main. Usage: scripts/integrate-verify-lane.sh <lane-slug>
set -euo pipefail
LANE="${1:?usage: $0 <lane-slug>}"
BRANCH="lane/$LANE"
REPO_ROOT=$(git rev-parse --show-toplevel)
TMP_WT=$(mktemp -d "/tmp/integrate-verify-$LANE.XXXX")
CANDIDATE="integrate/verify-$LANE"

cleanup() {
    git -C "$REPO_ROOT" worktree remove --force "$TMP_WT" 2>/dev/null || true
    git -C "$REPO_ROOT" branch -D "$CANDIDATE" 2>/dev/null || true
}
trap cleanup EXIT

git -C "$REPO_ROOT" branch -f "$CANDIDATE" main
git -C "$REPO_ROOT" worktree add -q "$TMP_WT" "$CANDIDATE"
git -C "$TMP_WT" merge --no-ff --no-edit "$BRANCH" \
    || { echo "MERGE CONFLICT: resolve manually"; exit 2; }

cd "$TMP_WT"
FAIL=0
if [ -f package.json ]; then
    bun install --frozen-lockfile 2>/dev/null || bun install
    bun test || FAIL=1
fi
if [ -f pyproject.toml ]; then
    uv sync -q 2>/dev/null || true
    uv run pytest -q || FAIL=1
fi
if [ -x scripts/validate-run.sh ] && [ -d tests/fixtures/contracts/sample-run ]; then
    ./scripts/validate-run.sh tests/fixtures/contracts/sample-run || FAIL=1
fi

if [ "$FAIL" -eq 0 ]; then
    echo "VERIFY PASS: $BRANCH merges clean and gates are green"
else
    echo "VERIFY FAIL: $BRANCH (see output above)"
    exit 1
fi
