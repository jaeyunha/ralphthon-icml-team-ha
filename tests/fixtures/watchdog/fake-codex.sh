#!/bin/sh
set -eu

if [ "${1:-}" = "exec" ]; then
  shift
fi

: "${FAKE_CODEX_CASE:?set FAKE_CODEX_CASE to a scenario name}"
FAKE_CODEX_SCENARIO_SET=${FAKE_CODEX_SCENARIO_SET:-"$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/scenarios.json"}
FAKE_CODEX_WORKSPACE=${FAKE_CODEX_WORKSPACE:-$PWD}
FAKE_CODEX_STATE_FILE=${FAKE_CODEX_STATE_FILE:-$FAKE_CODEX_WORKSPACE/.fake-codex-state.json}
FAKE_CODEX_ACCESS_LOG=${FAKE_CODEX_ACCESS_LOG:-$FAKE_CODEX_WORKSPACE/.fake-codex-access.ndjson}
export FAKE_CODEX_CASE FAKE_CODEX_SCENARIO_SET FAKE_CODEX_WORKSPACE FAKE_CODEX_STATE_FILE FAKE_CODEX_ACCESS_LOG

exec python3 - "$@" <<'PY'
import datetime
import json
import os
import pathlib
import sys
import time

case = os.environ["FAKE_CODEX_CASE"]
scenario_set = pathlib.Path(os.environ["FAKE_CODEX_SCENARIO_SET"])
workspace = pathlib.Path(os.environ["FAKE_CODEX_WORKSPACE"]).resolve()
state_path = pathlib.Path(os.environ["FAKE_CODEX_STATE_FILE"])
access_log = pathlib.Path(os.environ["FAKE_CODEX_ACCESS_LOG"])

with scenario_set.open(encoding="utf-8") as handle:
    document = json.load(handle)
try:
    scenario = document["scenarios"][case]
except KeyError:
    print(f"fake-codex: unknown scenario: {case}", file=sys.stderr)
    raise SystemExit(64)

state = {"scenario": case, "attempt": 0}
if state_path.exists():
    with state_path.open(encoding="utf-8") as handle:
        state = json.load(handle)
attempt = int(state.get("attempt", 0)) + 1
state.update({
    "scenario": case,
    "attempt": attempt,
    "logical_identity": "reviewer-r2",
    "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
})
state_path.parent.mkdir(parents=True, exist_ok=True)
temporary_state = state_path.with_name(state_path.name + ".tmp")
with temporary_state.open("w", encoding="utf-8") as handle:
    json.dump(state, handle, sort_keys=True)
    handle.write("\n")
os.replace(temporary_state, state_path)

responses = scenario["responses"]
response = responses[min(attempt - 1, len(responses) - 1)]
heartbeat_path = workspace / "phases" / "initial-review" / "heartbeat.json"
heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
with heartbeat_path.open("w", encoding="utf-8") as handle:
    json.dump({
        "agent_id": "reviewer-r2",
        "phase": "initial-review",
        "attempt": attempt,
        "heartbeat_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }, handle, sort_keys=True)
    handle.write("\n")

read_path = response.get("read_path")
if read_path:
    candidate = (workspace / read_path).resolve()
    manifest_path = workspace / "allowed-inputs.json"
    allowed = False
    if manifest_path.exists():
        with manifest_path.open(encoding="utf-8") as handle:
            manifest = json.load(handle)
        entries = manifest.get("paths") or manifest.get("allowed_inputs") or manifest.get("inputs") or []
        run_root = pathlib.Path(os.environ.get("RALPH_RUN_ROOT", workspace)).resolve()
        for entry in entries:
            path_value = entry.get("path") if isinstance(entry, dict) else entry
            if not isinstance(path_value, str):
                continue
            allowed_path = pathlib.Path(path_value)
            allowed_path = allowed_path.resolve() if allowed_path.is_absolute() else (run_root / allowed_path).resolve()
            if candidate == allowed_path or allowed_path in candidate.parents:
                allowed = True
                break
    readable = False
    try:
        candidate.read_bytes()
        readable = True
    except OSError:
        pass
    access_log.parent.mkdir(parents=True, exist_ok=True)
    with access_log.open("a", encoding="utf-8") as handle:
        json.dump({
            "attempt": attempt,
            "requested_path": read_path,
            "resolved_path": str(candidate),
            "allowed": allowed,
            "readable": readable,
        }, handle, sort_keys=True)
        handle.write("\n")

sleep_seconds = float(response.get("sleep_seconds", 0))
if sleep_seconds:
    time.sleep(sleep_seconds)

artifact_path_value = response.get("artifact_path")
if artifact_path_value:
    artifact_path = (workspace / artifact_path_value).resolve()
    if artifact_path != workspace and workspace not in artifact_path.parents:
        print("fake-codex: artifact path escapes workspace", file=sys.stderr)
        raise SystemExit(65)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    if "artifact_raw" in response:
        artifact_path.write_text(response["artifact_raw"], encoding="utf-8")
    elif "artifact" in response:
        temporary_artifact = artifact_path.with_name(artifact_path.name + ".tmp")
        with temporary_artifact.open("w", encoding="utf-8") as handle:
            json.dump(response["artifact"], handle, sort_keys=True)
            handle.write("\n")
        os.replace(temporary_artifact, artifact_path)

stderr = response.get("stderr")
if stderr:
    print(stderr, file=sys.stderr)
promise = response.get("promise")
if promise:
    print(f"<promise>{promise}</promise>")
raise SystemExit(int(response.get("exit_code", 0)))
PY
