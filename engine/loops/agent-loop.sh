#!/usr/bin/env bash
# Run exactly one coherent role/phase work item.
set -Eeuo pipefail

readonly EXIT_REOPEN=20
readonly EXIT_BLOCKED=21
readonly EXIT_POLICY_BLOCKED=22
readonly EXIT_TIMEOUT=124

usage() {
  cat <<'EOF'
Usage: agent-loop.sh [options]

Required:
  --agent-id ID              Persistent logical agent identifier
  --role ROLE                Role directory name under roles/
  --phase PHASE              Phase directory name under roles/ROLE/phases/
  --workspace PATH           Persistent agent workspace
  --task-context PATH        Current single-work-item context file
  --output-schema PATH       JSON Schema for the emitted artifact
  --artifact PATH            Artifact the invocation must emit

Optional:
  --repo-root PATH           Repository root (default: current directory)
  --policy PATH              Common policy prompt
  --rubric PATH              Venue rubric prompt
  --role-prompt PATH         Role PROMPT.base.md
  --phase-prompt PATH        Phase PROMPT.md
  --persona PATH             Persistent persona JSON
  --ledger PATH              Persistent ledger input; repeatable
  --allow PATH               Additional readable manifest path; repeatable
  --timeout SECONDS          Invocation wall-clock timeout (default: 1800)
  --heartbeat-interval SEC   Heartbeat interval (default: 10)
  --kill-grace SECONDS       TERM-to-KILL grace period (default: 5)
  --agent-command PATH       Agent executable (default: codex)
  --agent-arg ARG            Additional agent argument; repeatable
  --manifest-generator PATH  W0 manifest adapter executable
  --artifact-validator PATH  W0 artifact validator executable
  --manifest PATH            Manifest output (default: WORKSPACE/allowed-inputs.json)
  --result PATH              Result JSON output
  --reopen-feedback PATH     Exact checker feedback output
  -h, --help                 Show this help

Adapter contracts:
  manifest generator:
    TOOL --repo-root R --workspace W --agent-id A --role R --phase P
         --output FILE [--allow PATH ...]
  artifact validator:
    TOOL --artifact FILE --schema FILE --workspace W --role R --phase P

The adapter must return nonzero on failure and print exact diagnostic feedback.
When no adapter is supplied, the runner uses its built-in JSON manifest and
JSON-Schema validation fallbacks. Agent overrides receive the prompt on stdin.

Exit codes:
  0    NEXT or COMPLETE with a schema-valid artifact
  20   invocation reopened with exact feedback
  21   agent reported BLOCKED with a reason
  22   allowed-input manifest policy violation
  124  invocation timed out
  other agent process failure code (1 is used when the process dies by signal)
EOF
}

die() {
  printf 'agent-loop: %s\n' "$*" >&2
  exit 2
}

require_value() {
  [[ $# -ge 2 && -n "${2:-}" ]] || die "$1 requires a value"
}

REPO_ROOT=""
AGENT_ID=""
ROLE=""
PHASE=""
WORKSPACE=""
TASK_CONTEXT=""
OUTPUT_SCHEMA=""
ARTIFACT=""
POLICY=""
RUBRIC=""
ROLE_PROMPT=""
PHASE_PROMPT=""
PERSONA=""
TIMEOUT_SECONDS="${AGENT_LOOP_TIMEOUT_SECONDS:-1800}"
HEARTBEAT_INTERVAL="${AGENT_LOOP_HEARTBEAT_INTERVAL:-10}"
KILL_GRACE_SECONDS="${AGENT_LOOP_KILL_GRACE_SECONDS:-5}"
AGENT_COMMAND="${AGENT_LOOP_AGENT_COMMAND:-}"
MANIFEST_GENERATOR="${RALPH_MANIFEST_GENERATOR:-}"
ARTIFACT_VALIDATOR="${RALPH_ARTIFACT_VALIDATOR:-}"
MANIFEST_PATH=""
RESULT_PATH=""
REOPEN_FEEDBACK_PATH=""
LEDGERS=()
ALLOW_PATHS=()
AGENT_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root) require_value "$@"; REPO_ROOT=$2; shift 2 ;;
    --agent-id) require_value "$@"; AGENT_ID=$2; shift 2 ;;
    --role) require_value "$@"; ROLE=$2; shift 2 ;;
    --phase) require_value "$@"; PHASE=$2; shift 2 ;;
    --workspace) require_value "$@"; WORKSPACE=$2; shift 2 ;;
    --task-context) require_value "$@"; TASK_CONTEXT=$2; shift 2 ;;
    --output-schema) require_value "$@"; OUTPUT_SCHEMA=$2; shift 2 ;;
    --artifact) require_value "$@"; ARTIFACT=$2; shift 2 ;;
    --policy) require_value "$@"; POLICY=$2; shift 2 ;;
    --rubric) require_value "$@"; RUBRIC=$2; shift 2 ;;
    --role-prompt) require_value "$@"; ROLE_PROMPT=$2; shift 2 ;;
    --phase-prompt) require_value "$@"; PHASE_PROMPT=$2; shift 2 ;;
    --persona) require_value "$@"; PERSONA=$2; shift 2 ;;
    --ledger) require_value "$@"; LEDGERS+=("$2"); shift 2 ;;
    --allow) require_value "$@"; ALLOW_PATHS+=("$2"); shift 2 ;;
    --timeout) require_value "$@"; TIMEOUT_SECONDS=$2; shift 2 ;;
    --heartbeat-interval) require_value "$@"; HEARTBEAT_INTERVAL=$2; shift 2 ;;
    --kill-grace) require_value "$@"; KILL_GRACE_SECONDS=$2; shift 2 ;;
    --agent-command) require_value "$@"; AGENT_COMMAND=$2; shift 2 ;;
    --agent-arg) require_value "$@"; AGENT_ARGS+=("$2"); shift 2 ;;
    --manifest-generator) require_value "$@"; MANIFEST_GENERATOR=$2; shift 2 ;;
    --artifact-validator) require_value "$@"; ARTIFACT_VALIDATOR=$2; shift 2 ;;
    --manifest) require_value "$@"; MANIFEST_PATH=$2; shift 2 ;;
    --result) require_value "$@"; RESULT_PATH=$2; shift 2 ;;
    --reopen-feedback) require_value "$@"; REOPEN_FEEDBACK_PATH=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    --) shift; AGENT_ARGS+=("$@"); break ;;
    *) die "unknown option: $1" ;;
  esac
done

command -v python3 >/dev/null 2>&1 || die "python3 is required for the contract fallbacks"

[[ -n "$AGENT_ID" ]] || die "--agent-id is required"
[[ -n "$ROLE" ]] || die "--role is required"
[[ -n "$PHASE" ]] || die "--phase is required"
[[ -n "$WORKSPACE" ]] || die "--workspace is required"
[[ -n "$TASK_CONTEXT" ]] || die "--task-context is required"
[[ -n "$OUTPUT_SCHEMA" ]] || die "--output-schema is required"
[[ -n "$ARTIFACT" ]] || die "--artifact is required"
[[ "$TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]] || die "--timeout must be a positive integer"
[[ "$HEARTBEAT_INTERVAL" =~ ^[1-9][0-9]*$ ]] || die "--heartbeat-interval must be a positive integer"
[[ "$KILL_GRACE_SECONDS" =~ ^[0-9]+$ ]] || die "--kill-grace must be a non-negative integer"

REPO_ROOT=${REPO_ROOT:-$(pwd)}
RUN_ROOT=${AGENT_LOOP_RUN_ROOT:-${WATCHDOG_RUN_DIR:-"$(dirname "$(dirname "$WORKSPACE")")"}}
ROLE_DIR="$REPO_ROOT/roles/$ROLE"
PHASE_SPEC_DIR="$ROLE_DIR/phases/$PHASE"
POLICY=${POLICY:-"$REPO_ROOT/shared/COMMON_AGENT_POLICY.md"}
RUBRIC=${RUBRIC:-"$REPO_ROOT/shared/ICML_2026_REVIEW_RUBRIC.md"}
ROLE_PROMPT=${ROLE_PROMPT:-"$ROLE_DIR/PROMPT.base.md"}
PHASE_PROMPT=${PHASE_PROMPT:-"$PHASE_SPEC_DIR/PROMPT.md"}
PERSONA=${PERSONA:-"$WORKSPACE/persona.json"}
PHASE_DIR="$WORKSPACE/phases/$PHASE"
MANIFEST_PATH=${MANIFEST_PATH:-"$WORKSPACE/allowed-inputs.json"}
RESULT_PATH=${RESULT_PATH:-"$PHASE_DIR/invocation-result.json"}
REOPEN_FEEDBACK_PATH=${REOPEN_FEEDBACK_PATH:-"$PHASE_DIR/reopen-feedback.txt"}
HEARTBEAT_PATH=${AGENT_LOOP_HEARTBEAT_PATH:-"$WORKSPACE/heartbeat"}
ACCESS_LOG_PATH=${AGENT_LOOP_ACCESS_LOG:-"$PHASE_DIR/accessed-paths.log"}
STDOUT_PATH=${AGENT_LOOP_STDOUT_PATH:-"$PHASE_DIR/stdout.log"}
STDERR_PATH=${AGENT_LOOP_STDERR_PATH:-"$PHASE_DIR/stderr.log"}

mkdir -p "$WORKSPACE" "$PHASE_DIR" "$(dirname "$ARTIFACT")" \
  "$(dirname "$MANIFEST_PATH")" "$(dirname "$RESULT_PATH")" \
  "$(dirname "$REOPEN_FEEDBACK_PATH")"

canonical_path() {
  python3 - "$1" <<'PY'
import os, sys
print(os.path.realpath(os.path.abspath(sys.argv[1])))
PY
}

REPO_ROOT=$(canonical_path "$REPO_ROOT")
WORKSPACE=$(canonical_path "$WORKSPACE")
RUN_ROOT=$(canonical_path "$RUN_ROOT")
TASK_CONTEXT=$(canonical_path "$TASK_CONTEXT")
OUTPUT_SCHEMA=$(canonical_path "$OUTPUT_SCHEMA")
ARTIFACT=$(canonical_path "$ARTIFACT")
POLICY=$(canonical_path "$POLICY")
RUBRIC=$(canonical_path "$RUBRIC")
ROLE_PROMPT=$(canonical_path "$ROLE_PROMPT")
PHASE_PROMPT=$(canonical_path "$PHASE_PROMPT")
PERSONA=$(canonical_path "$PERSONA")
PHASE_DIR=$(canonical_path "$PHASE_DIR")
MANIFEST_PATH=$(canonical_path "$MANIFEST_PATH")
RESULT_PATH=$(canonical_path "$RESULT_PATH")
REOPEN_FEEDBACK_PATH=$(canonical_path "$REOPEN_FEEDBACK_PATH")
HEARTBEAT_PATH=$(canonical_path "$HEARTBEAT_PATH")
ACCESS_LOG_PATH=$(canonical_path "$ACCESS_LOG_PATH")
STDOUT_PATH=$(canonical_path "$STDOUT_PATH")
STDERR_PATH=$(canonical_path "$STDERR_PATH")

for required_file in "$POLICY" "$RUBRIC" "$ROLE_PROMPT" "$PHASE_PROMPT" "$TASK_CONTEXT" "$OUTPUT_SCHEMA"; do
  [[ -f "$required_file" ]] || die "required prompt input not found: $required_file"
done

contains_prd_path() {
  local candidate base
  candidate=$1
  base=${candidate##*/}
  [[ "$base" == "PRD.md" || "$candidate" == */PRD.md/* ]]
}

for prompt_path in "$POLICY" "$RUBRIC" "$ROLE_PROMPT" "$PHASE_PROMPT" "$PERSONA" "$TASK_CONTEXT" "$OUTPUT_SCHEMA"; do
  contains_prd_path "$prompt_path" && die "PRD.md must never be injected or allowed: $prompt_path"
done
if [[ ${#LEDGERS[@]} -gt 0 ]]; then
  for prompt_path in "${LEDGERS[@]}"; do
    contains_prd_path "$prompt_path" && die "PRD.md must never be injected or allowed: $prompt_path"
  done
fi
if [[ ${#ALLOW_PATHS[@]} -gt 0 ]]; then
  for prompt_path in "${ALLOW_PATHS[@]}"; do
    contains_prd_path "$prompt_path" && die "PRD.md must never be injected or allowed: $prompt_path"
  done
fi

if [[ ${#LEDGERS[@]} -eq 0 ]]; then
  case "$ROLE" in
    reviewer) DEFAULT_LEDGERS=(concern-ledger.json question-ledger.json score-history.json literature-registry.json) ;;
    author) DEFAULT_LEDGERS=(response-matrix.json) ;;
    *) DEFAULT_LEDGERS=() ;;
  esac
  for prompt_path in "${DEFAULT_LEDGERS[@]}"; do
    [[ -f "$WORKSPACE/$prompt_path" ]] && LEDGERS+=("$WORKSPACE/$prompt_path")
  done
fi

NORMALIZED_LEDGERS=()
if [[ ${#LEDGERS[@]} -gt 0 ]]; then
  for prompt_path in "${LEDGERS[@]}"; do
    prompt_path=$(canonical_path "$prompt_path")
    [[ -f "$prompt_path" ]] || die "ledger input not found: $prompt_path"
    NORMALIZED_LEDGERS+=("$prompt_path")
  done
  LEDGERS=("${NORMALIZED_LEDGERS[@]}")
fi

NORMALIZED_ALLOWS=()
if [[ ${#ALLOW_PATHS[@]} -gt 0 ]]; then
  for prompt_path in "${ALLOW_PATHS[@]}"; do
    prompt_path=$(canonical_path "$prompt_path")
    [[ -e "$prompt_path" ]] || die "allowed input not found: $prompt_path"
    NORMALIZED_ALLOWS+=("$prompt_path")
  done
  ALLOW_PATHS=("${NORMALIZED_ALLOWS[@]}")
fi

TMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/agent-loop.XXXXXX")
CHILD_PID=""
HEARTBEAT_PID=""
TIMER_PID=""
TIMED_OUT_MARKER="$TMP_ROOT/timed-out"
PROMPT_PATH="$TMP_ROOT/prompt.txt"
VALIDATOR_OUTPUT="$TMP_ROOT/validator-output.txt"
PARSED_PROMISE="$TMP_ROOT/promise.json"
ALLOW_LIST="$TMP_ROOT/allow-list.txt"

cleanup() {
  [[ -n "$HEARTBEAT_PID" ]] && kill "$HEARTBEAT_PID" 2>/dev/null || true
  [[ -n "$TIMER_PID" ]] && kill "$TIMER_PID" 2>/dev/null || true
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

sha256_file() {
  local path=$1
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$path" | cut -d ' ' -f 1
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$path" | cut -d ' ' -f 1
  elif command -v openssl >/dev/null 2>&1; then
    openssl dgst -sha256 "$path" | awk '{print $NF}'
  else
    python3 - "$path" <<'PY'
import hashlib, sys
h = hashlib.sha256()
with open(sys.argv[1], 'rb') as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b''):
        h.update(chunk)
print(h.hexdigest())
PY
  fi
}

atomic_text() {
  local destination=$1 content=$2 temporary
  temporary="$destination.tmp.$$"
  printf '%s\n' "$content" > "$temporary"
  mv "$temporary" "$destination"
}

write_result() {
  local status=$1 promise=${2:-} reason=${3:-} exit_code=${4:-0} artifact_hash=${5:-}
  python3 - "$RESULT_PATH" "$status" "$promise" "$reason" "$exit_code" \
    "$MANIFEST_HASH" "$artifact_hash" "$ARTIFACT" "$AGENT_ID" "$ROLE" "$PHASE" <<'PY'
import datetime, json, os, sys
(path, status, promise, reason, exit_code, manifest_hash, artifact_hash,
 artifact, agent_id, role, phase) = sys.argv[1:]
data = {
    "schema_version": 1,
    "agent_id": agent_id,
    "role": role,
    "phase": phase,
    "status": status,
    "promise": promise or None,
    "reason": reason or None,
    "exit_code": int(exit_code),
    "allowed_input_manifest_hash": manifest_hash,
    "artifact_path": artifact,
    "artifact_hash": artifact_hash or None,
    "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
}
temporary = path + ".tmp." + str(os.getpid())
with open(temporary, "w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2, sort_keys=True)
    handle.write("\n")
os.replace(temporary, path)
PY
}

reopen() {
  local feedback=$1 exit_code=${2:-$EXIT_REOPEN}
  atomic_text "$REOPEN_FEEDBACK_PATH" "$feedback"
  write_result "reopen" "" "$feedback" "$exit_code" ""
  printf '%s\n' "$feedback" >&2
  exit "$exit_code"
}

# Every prompt-visible source is also represented in the fallback manifest.
MANIFEST_INPUTS=("$POLICY" "$RUBRIC" "$ROLE_PROMPT" "$PHASE_PROMPT")
[[ -f "$PERSONA" ]] && MANIFEST_INPUTS+=("$PERSONA")
if [[ ${#LEDGERS[@]} -gt 0 ]]; then
  for prompt_path in "${LEDGERS[@]}"; do MANIFEST_INPUTS+=("$prompt_path"); done
fi
MANIFEST_INPUTS+=("$TASK_CONTEXT" "$OUTPUT_SCHEMA")
if [[ ${#ALLOW_PATHS[@]} -gt 0 ]]; then
  for prompt_path in "${ALLOW_PATHS[@]}"; do MANIFEST_INPUTS+=("$prompt_path"); done
fi
printf '%s\n' "${MANIFEST_INPUTS[@]}" > "$ALLOW_LIST"

if [[ -z "$MANIFEST_GENERATOR" && -x "$REPO_ROOT/packages/contracts/bin/generate-allowed-inputs" ]]; then
  MANIFEST_GENERATOR="$REPO_ROOT/packages/contracts/bin/generate-allowed-inputs"
fi

if [[ -n "$MANIFEST_GENERATOR" ]]; then
  [[ -x "$MANIFEST_GENERATOR" ]] || die "manifest generator is not executable: $MANIFEST_GENERATOR"
  GENERATOR_ARGS=(
    --repo-root "$REPO_ROOT"
    --workspace "$WORKSPACE"
    --agent-id "$AGENT_ID"
    --role "$ROLE"
    --phase "$PHASE"
    --output "$MANIFEST_PATH"
  )
  for prompt_path in "${MANIFEST_INPUTS[@]}"; do
    GENERATOR_ARGS+=(--allow "$prompt_path")
  done
  "$MANIFEST_GENERATOR" "${GENERATOR_ARGS[@]}" || die "manifest generator failed"
else
  python3 - "$ALLOW_LIST" "$MANIFEST_PATH" "$AGENT_ID" "$ROLE" "$PHASE" <<'PY'
import datetime, json, os, sys
source, destination, agent_id, role, phase = sys.argv[1:]
seen = set()
paths = []
with open(source, encoding="utf-8") as handle:
    for line in handle:
        path = os.path.realpath(os.path.abspath(line.rstrip("\n")))
        if path and path not in seen:
            seen.add(path)
            paths.append(path)
data = {
    "schema_version": 1,
    "agent_id": agent_id,
    "role": role,
    "phase": phase,
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
    "paths": paths,
    "allowed_inputs": [{"path": path, "access": "read"} for path in paths],
}
temporary = destination + ".tmp." + str(os.getpid())
with open(temporary, "w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2, sort_keys=True)
    handle.write("\n")
os.replace(temporary, destination)
PY
fi

[[ -f "$MANIFEST_PATH" ]] || die "manifest generator did not create: $MANIFEST_PATH"
python3 - "$MANIFEST_PATH" <<'PY'
import json, os, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    manifest = json.load(handle)
paths = []
for key in ("paths", "allowed_inputs", "inputs"):
    value = manifest.get(key, []) if isinstance(manifest, dict) else []
    if isinstance(value, list):
        for entry in value:
            path = entry.get("path") if isinstance(entry, dict) else entry
            if isinstance(path, str):
                paths.append(path)
if not paths:
    raise SystemExit("allowed-input manifest contains no paths")
for path in paths:
    pieces = os.path.normpath(path).split(os.sep)
    if "PRD.md" in pieces:
        raise SystemExit("allowed-input manifest must not contain PRD.md")
PY
MANIFEST_HASH=$(python3 - "$MANIFEST_PATH" <<'PY'
import json, re, sys
try:
    value = json.load(open(sys.argv[1], encoding="utf-8")).get("manifest_hash", "")
except (AttributeError, OSError, ValueError):
    value = ""
print(value if re.fullmatch(r"sha256:[a-f0-9]{64}", value) else "")
PY
)
[[ -n "$MANIFEST_HASH" ]] || MANIFEST_HASH="sha256:$(sha256_file "$MANIFEST_PATH")"
atomic_text "$MANIFEST_PATH.sha256" "$MANIFEST_HASH"

append_prompt_file() {
  local title=$1 path=$2
  printf '\n\n===== %s =====\n' "$title" >> "$PROMPT_PATH"
  command cat "$path" >> "$PROMPT_PATH"
  printf '\n' >> "$PROMPT_PATH"
}

: > "$PROMPT_PATH"
append_prompt_file "COMMON AGENT POLICY" "$POLICY"
append_prompt_file "ICML REVIEW RUBRIC" "$RUBRIC"
append_prompt_file "ROLE PROMPT" "$ROLE_PROMPT"
append_prompt_file "PHASE PROMPT" "$PHASE_PROMPT"
[[ -f "$PERSONA" ]] && append_prompt_file "PERSISTENT PERSONA" "$PERSONA"
if [[ ${#LEDGERS[@]} -gt 0 ]]; then
  for prompt_path in "${LEDGERS[@]}"; do
    append_prompt_file "PERSISTENT LEDGER: ${prompt_path##*/}" "$prompt_path"
  done
fi
append_prompt_file "ALLOWED INPUT MANIFEST (sha256: ${MANIFEST_HASH#sha256:})" "$MANIFEST_PATH"
[[ -s "$REOPEN_FEEDBACK_PATH" ]] && append_prompt_file "EXACT REOPEN FEEDBACK" "$REOPEN_FEEDBACK_PATH"
append_prompt_file "CURRENT SINGLE WORK ITEM" "$TASK_CONTEXT"
append_prompt_file "REQUIRED OUTPUT SCHEMA" "$OUTPUT_SCHEMA"
printf '\n\nWrite the artifact only to: %s\n' "$ARTIFACT" >> "$PROMPT_PATH"
printf 'The process working directory is the persistent workspace: %s\n' "$WORKSPACE" >> "$PROMPT_PATH"
printf 'Resolve relative allowed-input manifest paths against the run root: %s\n' "$RUN_ROOT" >> "$PROMPT_PATH"
printf 'Finish with exactly one promise token described by COMMON AGENT POLICY.\n' >> "$PROMPT_PATH"

# Defensive assertion: the runner never composes the design-time PRD file.
if python3 - "$PROMPT_PATH" <<'PY'
import sys
# Section labels expose source names. A PRD section would be an implementation error.
text = open(sys.argv[1], encoding="utf-8").read()
raise SystemExit(0 if "===== PRD" in text else 1)
PY
then
  die "internal prompt composition attempted to include PRD.md"
fi

: > "$STDOUT_PATH"
: > "$STDERR_PATH"
: > "$ACCESS_LOG_PATH"

if [[ -z "$AGENT_COMMAND" ]]; then
  AGENT_CMD=(codex exec --dangerously-bypass-approvals-and-sandbox -)
else
  AGENT_CMD=("$AGENT_COMMAND")
fi
if [[ ${#AGENT_ARGS[@]} -gt 0 ]]; then
  for prompt_path in "${AGENT_ARGS[@]}"; do AGENT_CMD+=("$prompt_path"); done
fi
command -v "${AGENT_CMD[0]}" >/dev/null 2>&1 || die "agent command not found: ${AGENT_CMD[0]}"

heartbeat_once() {
  local now temporary
  now=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
  temporary="$HEARTBEAT_PATH.tmp.$$"
  printf '%s\n' "$now" > "$temporary"
  mv "$temporary" "$HEARTBEAT_PATH"
}

heartbeat_loop() {
  while :; do
    heartbeat_once
    sleep "$HEARTBEAT_INTERVAL"
  done
}

handle_signal() {
  local signal=$1 exit_code=$2
  trap - TERM INT HUP
  if [[ -n "$CHILD_PID" ]] && kill -0 "$CHILD_PID" 2>/dev/null; then
    kill -s "$signal" "$CHILD_PID" 2>/dev/null || true
    wait "$CHILD_PID" 2>/dev/null || true
  fi
  [[ -n "$HEARTBEAT_PID" ]] && kill "$HEARTBEAT_PID" 2>/dev/null || true
  [[ -n "$TIMER_PID" ]] && kill "$TIMER_PID" 2>/dev/null || true
  write_result "interrupted" "" "received $signal; child signal forwarded" "$exit_code" ""
  exit "$exit_code"
}
trap 'handle_signal TERM 143' TERM
trap 'handle_signal INT 130' INT
trap 'handle_signal HUP 129' HUP

export RALPH_AGENT_ID="$AGENT_ID"
export RALPH_ROLE="$ROLE"
export RALPH_PHASE="$PHASE"
export RALPH_WORKSPACE="$WORKSPACE"
export RALPH_RUN_ROOT="$RUN_ROOT"
export RALPH_ALLOWED_INPUTS="$MANIFEST_PATH"
export RALPH_ALLOWED_INPUTS_HASH="$MANIFEST_HASH"
export RALPH_OUTPUT_ARTIFACT="$ARTIFACT"
export RALPH_OUTPUT_SCHEMA="$OUTPUT_SCHEMA"
export RALPH_TASK_CONTEXT="$TASK_CONTEXT"
export RALPH_ACCESSED_PATHS_LOG="$ACCESS_LOG_PATH"

heartbeat_once
(
  cd "$WORKSPACE"
  exec "${AGENT_CMD[@]}"
) < "$PROMPT_PATH" > "$STDOUT_PATH" 2> "$STDERR_PATH" &
CHILD_PID=$!
heartbeat_loop > /dev/null 2> /dev/null &
HEARTBEAT_PID=$!
(
  sleep "$TIMEOUT_SECONDS"
  if kill -0 "$CHILD_PID" 2>/dev/null; then
    : > "$TIMED_OUT_MARKER"
    kill -TERM "$CHILD_PID" 2>/dev/null || true
    sleep "$KILL_GRACE_SECONDS"
    kill -KILL "$CHILD_PID" 2>/dev/null || true
  fi
) > /dev/null 2> /dev/null &
TIMER_PID=$!

set +e
wait "$CHILD_PID"
AGENT_EXIT=$?
set -e
kill "$HEARTBEAT_PID" 2>/dev/null || true
kill "$TIMER_PID" 2>/dev/null || true
wait "$HEARTBEAT_PID" 2>/dev/null || true
wait "$TIMER_PID" 2>/dev/null || true
HEARTBEAT_PID=""
TIMER_PID=""
CHILD_PID=""
heartbeat_once

if [[ -f "$TIMED_OUT_MARKER" ]]; then
  write_result "time_exhausted" "" "agent invocation exceeded ${TIMEOUT_SECONDS}s" "$EXIT_TIMEOUT" ""
  exit "$EXIT_TIMEOUT"
fi

# A fake agent or instrumented provider records one accessed path per line here.
# This is an enforcement adapter for integration tests and audited providers; the
# production workspace must still be provisioned from the same manifest.
if [[ -s "$ACCESS_LOG_PATH" ]]; then
  set +e
  ACCESS_FEEDBACK=$(python3 - "$MANIFEST_PATH" "$ACCESS_LOG_PATH" "$WORKSPACE" "$ARTIFACT" "$RUN_ROOT" <<'PY'
import json, os, sys
manifest_path, log_path, workspace, artifact, run_root = sys.argv[1:]
manifest = json.load(open(manifest_path, encoding="utf-8"))
allowed = [os.path.realpath(manifest_path), os.path.realpath(artifact)]
for key in ("paths", "allowed_inputs", "inputs"):
    value = manifest.get(key, []) if isinstance(manifest, dict) else []
    if not isinstance(value, list):
        continue
    for entry in value:
        path = entry.get("path") if isinstance(entry, dict) else entry
        if isinstance(path, str):
            allowed.append(os.path.realpath(path if os.path.isabs(path) else os.path.join(run_root, path)))

def permitted(path):
    actual = os.path.realpath(path if os.path.isabs(path) else os.path.join(workspace, path))
    for root in allowed:
        if actual == root or actual.startswith(root.rstrip(os.sep) + os.sep):
            return True
    return False

violations = []
with open(log_path, encoding="utf-8") as handle:
    for raw in handle:
        raw = raw.strip()
        if not raw:
            continue
        # Accept either PATH or OP<TAB>PATH audit records.
        path = raw.split("\t", 1)[-1]
        if not permitted(path):
            violations.append(os.path.realpath(path if os.path.isabs(path) else os.path.join(workspace, path)))
if violations:
    print("Manifest violation: accessed path is not allowed: " + violations[0])
    raise SystemExit(1)
PY
)
  ACCESS_STATUS=$?
  set -e
  if [[ $ACCESS_STATUS -ne 0 ]]; then
    reopen "$ACCESS_FEEDBACK" "$EXIT_POLICY_BLOCKED"
  fi
fi

if [[ $AGENT_EXIT -ne 0 ]]; then
  FAILURE_REASON="agent command exited with status $AGENT_EXIT"
  [[ -s "$STDERR_PATH" ]] && FAILURE_REASON="$FAILURE_REASON: $(command cat "$STDERR_PATH")"
  write_result "agent_failed" "" "$FAILURE_REASON" "$AGENT_EXIT" ""
  exit "$AGENT_EXIT"
fi

set +e
PROMISE_FEEDBACK=$(python3 - "$STDOUT_PATH" "$PARSED_PROMISE" <<'PY'
import json, re, sys
stdout_path, result_path = sys.argv[1:]
text = open(stdout_path, encoding="utf-8", errors="replace").read()
pattern = re.compile(r"<promise>\s*(NEXT|COMPLETE|BLOCKED\s*:\s*[^<\r\n]+)\s*</promise>")
matches = pattern.findall(text)
if len(matches) == 0:
    print("Missing completion promise. Emit exactly one <promise>NEXT</promise>, <promise>COMPLETE</promise>, or <promise>BLOCKED: reason</promise>.")
    raise SystemExit(1)
if len(matches) > 1:
    print("Multiple completion promises emitted; emit exactly one promise token.")
    raise SystemExit(1)
raw = matches[0].strip()
if raw.startswith("BLOCKED"):
    reason = raw.split(":", 1)[1].strip()
    if not reason:
        print("BLOCKED promise requires a non-empty reason.")
        raise SystemExit(1)
    data = {"promise": "BLOCKED", "reason": reason}
else:
    data = {"promise": raw, "reason": ""}
with open(result_path, "w", encoding="utf-8") as handle:
    json.dump(data, handle)
PY
)
PROMISE_STATUS=$?
set -e
if [[ $PROMISE_STATUS -ne 0 ]]; then
  reopen "$PROMISE_FEEDBACK"
fi

PROMISE=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["promise"])' "$PARSED_PROMISE")
PROMISE_REASON=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["reason"])' "$PARSED_PROMISE")

if [[ "$PROMISE" == "BLOCKED" ]]; then
  atomic_text "$REOPEN_FEEDBACK_PATH" "$PROMISE_REASON"
  write_result "blocked" "$PROMISE" "$PROMISE_REASON" "$EXIT_BLOCKED" ""
  exit "$EXIT_BLOCKED"
fi

[[ -f "$ARTIFACT" ]] || reopen "Promise $PROMISE requires artifact at $ARTIFACT, but no artifact was emitted."

if [[ -z "$ARTIFACT_VALIDATOR" ]]; then
  if [[ -x "$REPO_ROOT/packages/contracts/bin/validate-artifact" ]]; then
    ARTIFACT_VALIDATOR="$REPO_ROOT/packages/contracts/bin/validate-artifact"
  elif [[ -x "$REPO_ROOT/packages/schemas/bin/validate-artifact" ]]; then
    ARTIFACT_VALIDATOR="$REPO_ROOT/packages/schemas/bin/validate-artifact"
  fi
fi

set +e
if [[ -n "$ARTIFACT_VALIDATOR" ]]; then
  [[ -x "$ARTIFACT_VALIDATOR" ]] || die "artifact validator is not executable: $ARTIFACT_VALIDATOR"
  "$ARTIFACT_VALIDATOR" \
    --artifact "$ARTIFACT" \
    --schema "$OUTPUT_SCHEMA" \
    --workspace "$WORKSPACE" \
    --role "$ROLE" \
    --phase "$PHASE" > "$VALIDATOR_OUTPUT" 2>&1
  VALIDATION_STATUS=$?
else
  python3 - "$ARTIFACT" "$OUTPUT_SCHEMA" > "$VALIDATOR_OUTPUT" 2>&1 <<'PY'
import json, re, sys
artifact_path, schema_path = sys.argv[1:]
try:
    with open(artifact_path, encoding="utf-8") as handle:
        instance = json.load(handle)
except Exception as error:
    print(f"Artifact is not valid JSON: {error}")
    raise SystemExit(1)
try:
    with open(schema_path, encoding="utf-8") as handle:
        schema = json.load(handle)
except Exception as error:
    print(f"Output schema is not valid JSON: {error}")
    raise SystemExit(1)

try:
    import jsonschema
except ImportError:
    jsonschema = None

if jsonschema is not None:
    try:
        validator_class = jsonschema.validators.validator_for(schema)
        validator_class.check_schema(schema)
        errors = sorted(validator_class(schema).iter_errors(instance), key=lambda error: list(error.absolute_path))
    except Exception as error:
        print(f"Output schema validation setup failed: {error}")
        raise SystemExit(1)
    if errors:
        for error in errors:
            location = "$" + "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.absolute_path)
            print(f"{location}: {error.message}")
        raise SystemExit(1)
    print("Artifact is schema-valid.")
    raise SystemExit(0)

# Dependency-free fallback for the JSON-Schema features used by role artifacts.
def resolve_ref(root, reference):
    if not reference.startswith("#/"):
        raise ValueError(f"unsupported non-local $ref: {reference}")
    value = root
    for token in reference[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        value = value[token]
    return value

def type_ok(value, expected):
    table = {
        "null": lambda item: item is None,
        "boolean": lambda item: isinstance(item, bool),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "string": lambda item: isinstance(item, str),
        "array": lambda item: isinstance(item, list),
        "object": lambda item: isinstance(item, dict),
    }
    return expected in table and table[expected](value)

def validate(value, rule, path="$", root=None):
    root = rule if root is None else root
    if isinstance(rule, bool):
        return [] if rule else [f"{path}: schema forbids this value"]
    if not isinstance(rule, dict):
        return [f"{path}: invalid schema node"]
    if "$ref" in rule:
        try:
            return validate(value, resolve_ref(root, rule["$ref"]), path, root)
        except Exception as error:
            return [f"{path}: could not resolve $ref: {error}"]
    errors = []
    expected = rule.get("type")
    if expected is not None:
        choices = expected if isinstance(expected, list) else [expected]
        if not any(type_ok(value, choice) for choice in choices):
            return [f"{path}: expected type {' or '.join(choices)}"]
    if "const" in rule and value != rule["const"]:
        errors.append(f"{path}: value does not match const")
    if "enum" in rule and value not in rule["enum"]:
        errors.append(f"{path}: value is not in enum")
    if "allOf" in rule:
        for subrule in rule["allOf"]:
            errors.extend(validate(value, subrule, path, root))
    if "anyOf" in rule and not any(not validate(value, subrule, path, root) for subrule in rule["anyOf"]):
        errors.append(f"{path}: value does not satisfy anyOf")
    if "oneOf" in rule and sum(not validate(value, subrule, path, root) for subrule in rule["oneOf"]) != 1:
        errors.append(f"{path}: value does not satisfy exactly one oneOf branch")
    if isinstance(value, dict):
        properties = rule.get("properties", {})
        for key in rule.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key}: required property is missing")
        for key, item in value.items():
            if key in properties:
                errors.extend(validate(item, properties[key], f"{path}.{key}", root))
            elif rule.get("additionalProperties") is False:
                errors.append(f"{path}.{key}: additional property is not allowed")
            elif isinstance(rule.get("additionalProperties"), dict):
                errors.extend(validate(item, rule["additionalProperties"], f"{path}.{key}", root))
        if len(value) < rule.get("minProperties", 0):
            errors.append(f"{path}: too few properties")
    if isinstance(value, list):
        if len(value) < rule.get("minItems", 0):
            errors.append(f"{path}: too few items")
        if "maxItems" in rule and len(value) > rule["maxItems"]:
            errors.append(f"{path}: too many items")
        if rule.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value):
            errors.append(f"{path}: items are not unique")
        if isinstance(rule.get("items"), dict):
            for index, item in enumerate(value):
                errors.extend(validate(item, rule["items"], f"{path}[{index}]", root))
    if isinstance(value, str):
        if len(value) < rule.get("minLength", 0):
            errors.append(f"{path}: string is shorter than minLength")
        if "maxLength" in rule and len(value) > rule["maxLength"]:
            errors.append(f"{path}: string is longer than maxLength")
        if "pattern" in rule and re.search(rule["pattern"], value) is None:
            errors.append(f"{path}: string does not match pattern")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in rule and value < rule["minimum"]:
            errors.append(f"{path}: number is below minimum")
        if "maximum" in rule and value > rule["maximum"]:
            errors.append(f"{path}: number is above maximum")
    return errors

errors = validate(instance, schema, root=schema)
if errors:
    print("\n".join(errors))
    raise SystemExit(1)
print("Artifact is schema-valid.")
PY
  VALIDATION_STATUS=$?
fi
set -e

if [[ $VALIDATION_STATUS -ne 0 ]]; then
  VALIDATION_FEEDBACK=$(command cat "$VALIDATOR_OUTPUT")
  [[ -n "$VALIDATION_FEEDBACK" ]] || VALIDATION_FEEDBACK="Artifact validation failed without diagnostic output."
  reopen "$VALIDATION_FEEDBACK"
fi

ARTIFACT_HASH="sha256:$(sha256_file "$ARTIFACT")"
rm -f "$REOPEN_FEEDBACK_PATH"
write_result "settled" "$PROMISE" "" 0 "$ARTIFACT_HASH"
printf '%s\n' "$PROMISE"
