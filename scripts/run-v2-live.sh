#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  printf '%s\n' 'Usage: run-v2-live.sh --run-dir DIR --config FILE --database-url URL --allowed-event-types FILE --ack-live-v2'
}

RUN_DIR=
CONFIG=
DATABASE_URL_VALUE=
ALLOWED_EVENT_TYPES=
ACK=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-dir) RUN_DIR=${2:?}; shift 2 ;;
    --config) CONFIG=${2:?}; shift 2 ;;
    --database-url) DATABASE_URL_VALUE=${2:?}; shift 2 ;;
    --allowed-event-types) ALLOWED_EVENT_TYPES=${2:?}; shift 2 ;;
    --ack-live-v2) ACK=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

[[ $ACK -eq 1 ]] || { printf '%s\n' 'error: live v2 execution requires --ack-live-v2' >&2; exit 2; }
[[ -n $RUN_DIR && -n $CONFIG && -n $DATABASE_URL_VALUE && -n $ALLOWED_EVENT_TYPES ]] || { usage >&2; exit 2; }
command -v bun >/dev/null || { printf '%s\n' 'error: bun is required' >&2; exit 127; }
command -v python3 >/dev/null || { printf '%s\n' 'error: python3 is required' >&2; exit 127; }
command -v docker >/dev/null || { printf '%s\n' 'error: Docker is required for live v2 execution' >&2; exit 127; }

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
RUN_DIR=$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve())' "$RUN_DIR")
CONFIG=$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve())' "$CONFIG")
ALLOWED_EVENT_TYPES=$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve())' "$ALLOWED_EVENT_TYPES")
mkdir -p "$RUN_DIR"

python3 - "$CONFIG" <<'PY'
import json, pathlib, sys
config = json.loads(pathlib.Path(sys.argv[1]).read_text())
phases = config.get("phase_runs")
if not isinstance(phases, list) or not phases:
    raise SystemExit("live v2 config requires non-empty phase_runs")
for phase in phases:
    if phase.get("held_supervisor_v2") is not True:
        raise SystemExit("every live v2 phase requires held_supervisor_v2=true")
    if phase.get("sandbox_capability") is not True or phase.get("broker_capability") is not True:
        raise SystemExit("every live v2 phase requires proven sandbox and broker capabilities")
PY

docker info >/dev/null
DATABASE_URL="$DATABASE_URL_VALUE" bun run --cwd "$REPO_ROOT/packages/db" db:migrate

WATCHDOG="$REPO_ROOT/engine/watchdog/committee-watchdog.sh"
EVENT_LOG="$RUN_DIR/events-v2.ndjson"
"$WATCHDOG" --run-dir "$RUN_DIR" --config "$CONFIG" &
WATCHDOG_PID=$!
cleanup() {
  if kill -0 "$WATCHDOG_PID" 2>/dev/null; then
    kill "$WATCHDOG_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

while kill -0 "$WATCHDOG_PID" 2>/dev/null; do
  if [[ -e $EVENT_LOG ]]; then
    bun run "$REPO_ROOT/engine/projector/src/run-projector-v2.ts" \
      --run-id "$(basename "$RUN_DIR")" \
      --event-log "$EVENT_LOG" \
      --database-url "$DATABASE_URL_VALUE" \
      --allowed-event-types "$ALLOWED_EVENT_TYPES" \
      --ack-live-v2
  fi
  sleep 0.1
done
wait "$WATCHDOG_PID"
WATCHDOG_STATUS=$?

if [[ -e $EVENT_LOG ]]; then
  bun run "$REPO_ROOT/engine/projector/src/run-projector-v2.ts" \
    --run-id "$(basename "$RUN_DIR")" \
    --event-log "$EVENT_LOG" \
    --database-url "$DATABASE_URL_VALUE" \
    --allowed-event-types "$ALLOWED_EVENT_TYPES" \
    --ack-live-v2
fi
trap - EXIT INT TERM
exit "$WATCHDOG_STATUS"
