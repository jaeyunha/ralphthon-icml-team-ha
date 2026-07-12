#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
command -v bun >/dev/null 2>&1 || {
  printf 'contracts-adapter: bun is required\n' >&2
  exit 127
}

command=${1:-}
[ -n "$command" ] || {
  printf 'usage: %s COMMAND [OPTIONS]\n' "$0" >&2
  exit 64
}
shift

case "$command" in
  generate-manifest|verify-manifest|phase-entry|run-transition)
    exec bun "$SCRIPT_DIR/contracts-adapter.ts" "$command" "$@"
    ;;
  --*)
    # agent-loop invokes the manifest generator directly with --repo-root first.
    exec bun "$SCRIPT_DIR/contracts-adapter.ts" generate-manifest "$command" "$@"
    ;;
  *)
    printf 'contracts-adapter: unknown command: %s\n' "$command" >&2
    exit 64
    ;;
esac
