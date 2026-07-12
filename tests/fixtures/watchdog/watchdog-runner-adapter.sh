#!/bin/sh
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
FAKE_CODEX=${FAKE_CODEX:-$ROOT/fake-codex.sh}
SCENARIOS=${WATCHDOG_SCENARIOS:-$ROOT/scenarios.json}
WORKSPACE=${WATCHDOG_AGENT_DIR:-${WATCHDOG_WORKSPACE:-$PWD}}
PHASE_DIR=${WATCHDOG_PHASE_DIR:-$WORKSPACE/phases/${WATCHDOG_PHASE:-initial-review}}
RESULT_PATH=${WATCHDOG_INVOCATION_RESULT:-$PHASE_DIR/invocation-result.json}
ARTIFACT_PATH=${WATCHDOG_ARTIFACT_PATH:-$PHASE_DIR/artifacts/review.json}
CASE=${WATCHDOG_FIXTURE_CASE:-happy-path}
OUTPUT=$PHASE_DIR/fake-codex.stdout
ERROR=$PHASE_DIR/fake-codex.stderr
ACCESS_LOG=$WORKSPACE/.fake-codex-access.ndjson
STATE_FILE=$WORKSPACE/.fake-codex-state.json
mkdir -p -- "$PHASE_DIR" "$PHASE_DIR/artifacts"

FAKE_CODEX_CASE=$CASE \
FAKE_CODEX_SCENARIO_SET=$SCENARIOS \
FAKE_CODEX_WORKSPACE=$WORKSPACE \
FAKE_CODEX_STATE_FILE=$STATE_FILE \
FAKE_CODEX_ACCESS_LOG=$ACCESS_LOG \
  "$FAKE_CODEX" exec --dangerously-bypass-approvals-and-sandbox >"$OUTPUT" 2>"$ERROR"
agent_rc=$?

python3 - "$CASE" "$agent_rc" "$OUTPUT" "$ERROR" "$ACCESS_LOG" "$ARTIFACT_PATH" "$RESULT_PATH" <<'PY'
import hashlib
import json
import os
import pathlib
import re
import sys

case, raw_rc, output_name, error_name, access_name, artifact_name, result_name = sys.argv[1:]
agent_rc = int(raw_rc)
output_path = pathlib.Path(output_name)
error_path = pathlib.Path(error_name)
access_path = pathlib.Path(access_name)
artifact_path = pathlib.Path(artifact_name)
result_path = pathlib.Path(result_name)
stdout = output_path.read_text(encoding="utf-8") if output_path.exists() else ""
stderr = error_path.read_text(encoding="utf-8") if error_path.exists() else ""
promise_match = re.search(r"<promise>(NEXT|COMPLETE|BLOCKED(?:: [^<]+)?)</promise>", stdout)
promise = promise_match.group(1) if promise_match else ""
violated = False
if access_path.exists():
    for line in access_path.read_text(encoding="utf-8").splitlines():
        if line and not json.loads(line).get("allowed", False):
            violated = True
            break

validated = False
artifact_hash = None
artifact_error = None
if artifact_path.exists():
    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        validated = (
            artifact.get("schema_version") == 1
            and artifact.get("agent_id") == "reviewer-r2"
            and artifact.get("phase") == "initial-review"
            and isinstance(artifact.get("artifact_version"), int)
            and artifact.get("decision") in {"continue", "complete", "blocked"}
        )
        if not validated:
            artifact_error = "schema mismatch"
    except json.JSONDecodeError:
        artifact_error = "invalid JSON"
    artifact_hash = "sha256:" + hashlib.sha256(artifact_path.read_bytes()).hexdigest()

if violated:
    status, reason = "blocked", "manifest violation: input outside allowed-inputs.json"
elif agent_rc != 0:
    status, reason = "failed", f"agent exited {agent_rc}: {stderr.strip()}"
elif promise == "COMPLETE" and not artifact_path.exists():
    status, reason = "next", "REOPEN: COMPLETE promise requires a schema-valid artifact"
elif promise == "COMPLETE" and not validated:
    status, reason = "next", f"REOPEN: artifact validation failed: {artifact_error or 'schema mismatch'}"
elif promise == "COMPLETE":
    status, reason = "complete", "schema-valid artifact and COMPLETE promise"
elif promise.startswith("BLOCKED"):
    status, reason = "blocked", promise.partition(": ")[2] or "agent blocked"
elif promise == "NEXT":
    status, reason = "next", "agent requested next work item"
else:
    status, reason = "next", "REOPEN: missing or malformed promise"

result = {
    "status": status,
    "validated": validated and not violated,
    "artifact_hash": artifact_hash,
    "reason": reason,
    "promise": promise or None,
    "agent_exit_code": agent_rc,
}
result_path.parent.mkdir(parents=True, exist_ok=True)
temporary = result_path.with_name(result_path.name + ".tmp")
temporary.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
os.replace(temporary, result_path)
PY

exit 0
