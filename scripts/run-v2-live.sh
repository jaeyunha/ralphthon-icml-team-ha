#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  printf '%s\n' 'Usage: run-v2-live.sh --run-id ID --run-dir DIR --config FILE --database-url URL --allowed-event-types FILE [--skip-migrate] [--projector-db-connections N] --ack-live-v2'
}

RUN_ID=
RUN_DIR=
CONFIG=
DATABASE_URL_VALUE=
ALLOWED_EVENT_TYPES=
ACK=0
MIGRATE=1
PROJECTOR_DB_CONNECTIONS=2
while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id) RUN_ID=${2:?}; shift 2 ;;
    --run-dir) RUN_DIR=${2:?}; shift 2 ;;
    --config) CONFIG=${2:?}; shift 2 ;;
    --database-url) DATABASE_URL_VALUE=${2:?}; shift 2 ;;
    --allowed-event-types) ALLOWED_EVENT_TYPES=${2:?}; shift 2 ;;
    --skip-migrate) MIGRATE=0; shift ;;
    --projector-db-connections) PROJECTOR_DB_CONNECTIONS=${2:?}; shift 2 ;;
    --ack-live-v2) ACK=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

[[ $ACK -eq 1 ]] || { printf '%s\n' 'error: live v2 execution requires --ack-live-v2' >&2; exit 2; }
[[ -n $RUN_ID && -n $RUN_DIR && -n $CONFIG && -n $DATABASE_URL_VALUE && -n $ALLOWED_EVENT_TYPES ]] || { usage >&2; exit 2; }
[[ $PROJECTOR_DB_CONNECTIONS =~ ^[1-9][0-9]*$ && $PROJECTOR_DB_CONNECTIONS -le 6 ]] || { printf '%s\n' 'error: --projector-db-connections must be an integer from 1 through 6' >&2; exit 2; }
command -v bun >/dev/null || { printf '%s\n' 'error: bun is required' >&2; exit 127; }
command -v python3 >/dev/null || { printf '%s\n' 'error: python3 is required' >&2; exit 127; }
command -v docker >/dev/null || { printf '%s\n' 'error: Docker is required for live v2 execution' >&2; exit 127; }
[[ -n ${V2_CAPABILITY_ATTESTOR:-} && -x ${V2_CAPABILITY_ATTESTOR:-} ]] || { printf '%s\n' 'error: V2_CAPABILITY_ATTESTOR must name the trusted capability attestor executable' >&2; exit 127; }

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
RUN_DIR_INPUT=$RUN_DIR
RUN_DIR=$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve())' "$RUN_DIR_INPUT")
CONFIG=$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve())' "$CONFIG")
ALLOWED_EVENT_TYPES=$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve())' "$ALLOWED_EVENT_TYPES")
[[ -f $CONFIG && -f $ALLOWED_EVENT_TYPES ]] || { printf '%s\n' 'error: config and allowed-event-types must be regular files' >&2; exit 2; }
mkdir -p "$RUN_DIR"

python3 - "$CONFIG" "$RUN_DIR_INPUT" "$RUN_ID" <<'PY'
import datetime as dt
import hashlib
import json
import os
import pathlib
import subprocess
import sys

config_path = pathlib.Path(sys.argv[1])
raw_root = pathlib.Path(sys.argv[2])
if raw_root.is_symlink():
    raise SystemExit("live v2 run directory must not be a symlink")
root = raw_root.resolve()
run_id = sys.argv[3]
config_bytes = config_path.read_bytes()
config = json.loads(config_bytes)
if not isinstance(config, dict) or config.get("run_id") != run_id:
    raise SystemExit("live v2 config run_id must exactly match --run-id")
phases = config.get("phase_runs")
if not isinstance(phases, list) or not phases:
    raise SystemExit("live v2 config requires non-empty phase_runs")
config_hash = "sha256:" + hashlib.sha256(config_bytes).hexdigest()
now = dt.datetime.now(dt.timezone.utc)
attestation_hashes = []
for phase in phases:
    if not isinstance(phase, dict):
        raise SystemExit("every phase must be an object")
    phase_id = phase.get("phase_run_id")
    if not isinstance(phase_id, str) or not phase_id:
        raise SystemExit("every live v2 phase requires phase_run_id")
    if "agent_command" in phase or "agent_args" in phase:
        raise SystemExit("live v2 phases must use the dedicated launcher; agent_command and agent_args are forbidden")
    launcher = phase.get("launcher")
    if not isinstance(launcher, dict) or launcher.get("kind") != "v2_dedicated_launcher":
        raise SystemExit("every live v2 phase requires launcher.kind=v2_dedicated_launcher")
    attestations = phase.get("attestations")
    if not isinstance(attestations, dict) or set(attestations) != {"custody", "sandbox", "broker", "denial"}:
        raise SystemExit("every phase requires exactly custody, sandbox, broker, and denial attestations")
    for kind, relative in attestations.items():
        if not isinstance(relative, str) or not relative:
            raise SystemExit(f"{phase_id} {kind} attestation path is invalid")
        path = (root / relative).resolve()
        if root not in path.parents or not path.is_file() or path.is_symlink():
            raise SystemExit(f"{phase_id} {kind} attestation must be a regular file inside run directory")
        raw = path.read_bytes()
        try:
            attestation = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{phase_id} {kind} attestation is not JSON") from exc
        if not isinstance(attestation, dict) or set(attestation) != {"version", "kind", "run_id", "phase_run_id", "config_hash", "issued_at", "issuer", "status"}:
            raise SystemExit(f"{phase_id} {kind} attestation has an unexpected schema")
        if (attestation.get("version") != 2 or attestation.get("kind") != kind or attestation.get("run_id") != run_id
                or attestation.get("phase_run_id") != phase_id or attestation.get("config_hash") != config_hash
                or attestation.get("issuer") != "v2-capability-attestor" or attestation.get("status") != "verified"):
            raise SystemExit(f"{phase_id} {kind} attestation is not a trusted v2 capability attestation")
        try:
            issued_at = dt.datetime.fromisoformat(attestation["issued_at"].replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError) as exc:
            raise SystemExit(f"{phase_id} {kind} attestation has invalid issued_at") from exc
        if issued_at.tzinfo is None or abs((now - issued_at).total_seconds()) > 300:
            raise SystemExit(f"{phase_id} {kind} attestation is not fresh")
        verifier = os.environ.get("V2_CAPABILITY_ATTESTOR")
        if not verifier:
            raise SystemExit("trusted v2 capability attestor is not configured")
        verified = subprocess.run(
            [verifier, "verify", "--run-dir", str(root), "--config-hash", config_hash, "--phase-run-id", phase_id, "--kind", kind, "--attestation", str(path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if verified.returncode != 0:
            raise SystemExit(f"{phase_id} {kind} attestation was not verified by the trusted attestor")
        attestation_hashes.append({"kind": kind, "path": relative, "hash": "sha256:" + hashlib.sha256(raw).hexdigest()})
identity = {"version": 2, "run_id": run_id, "config_hash": config_hash, "attestations": sorted(attestation_hashes, key=lambda value: (value["path"], value["kind"]))}
identity_path = root / ".v2-live-run-identity.json"
encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
try:
    descriptor = os.open(identity_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    existing = identity_path.read_bytes()
    if existing != encoded:
        raise SystemExit("run directory is already bound to a different live v2 identity")
else:
    with os.fdopen(descriptor, "wb") as output:
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())
PY

docker info >/dev/null
if [[ $MIGRATE -eq 1 ]]; then
  DATABASE_URL="$DATABASE_URL_VALUE" bun run --cwd "$REPO_ROOT/packages/db" db:migrate
fi

WATCHDOG="$REPO_ROOT/engine/watchdog/committee-watchdog.sh"
EVENT_LOG="$RUN_DIR/events-v2.ndjson"
PROJECTOR_MARKER="$RUN_DIR/control/.v2-projector-marker"
mkdir -p "$RUN_DIR/control"
python3 -c 'import os,sys; os.setsid(); os.execv(sys.argv[1], sys.argv[1:])' "$WATCHDOG" --run-dir "$RUN_DIR" --config "$CONFIG" &
WATCHDOG_PID=$!
WATCHDOG_STATUS=0
cleanup() {
  local signal_status=$1
  trap - EXIT INT TERM
  if kill -0 "$WATCHDOG_PID" 2>/dev/null; then
    kill -TERM -- "-$WATCHDOG_PID" 2>/dev/null || true
    for _ in {1..50}; do kill -0 "$WATCHDOG_PID" 2>/dev/null || break; sleep 0.1; done
    kill -KILL -- "-$WATCHDOG_PID" 2>/dev/null || true
  fi
  wait "$WATCHDOG_PID" 2>/dev/null || true
  exit "$signal_status"
}
trap 'cleanup $?' EXIT
trap 'cleanup 130' INT
trap 'cleanup 143' TERM

while kill -0 "$WATCHDOG_PID" 2>/dev/null; do
  if [[ -e $EVENT_LOG && ( ! -e $PROJECTOR_MARKER || $EVENT_LOG -nt $PROJECTOR_MARKER ) ]]; then
    bun run "$REPO_ROOT/engine/projector/src/run-projector-v2.ts" --run-id "$RUN_ID" --event-log "$EVENT_LOG" --database-url "$DATABASE_URL_VALUE" --database-max-connections "$PROJECTOR_DB_CONNECTIONS" --allowed-event-types "$ALLOWED_EVENT_TYPES" --ack-live-v2
    touch "$PROJECTOR_MARKER"
  fi
  sleep 0.5
done
if wait "$WATCHDOG_PID"; then WATCHDOG_STATUS=0; else WATCHDOG_STATUS=$?; fi
if [[ -e $EVENT_LOG ]]; then
  bun run "$REPO_ROOT/engine/projector/src/run-projector-v2.ts" --run-id "$RUN_ID" --event-log "$EVENT_LOG" --database-url "$DATABASE_URL_VALUE" --database-max-connections "$PROJECTOR_DB_CONNECTIONS" --allowed-event-types "$ALLOWED_EVENT_TYPES" --ack-live-v2
fi
trap - EXIT INT TERM
exit "$WATCHDOG_STATUS"
