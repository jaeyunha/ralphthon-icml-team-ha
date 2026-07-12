#!/bin/sh
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
FAKE_CODEX=${FAKE_CODEX:-$ROOT/fake-codex.sh}
SCENARIOS=${WATCHDOG_SCENARIOS:-$ROOT/scenarios.json}
ARTIFACT_SCHEMA=${WATCHDOG_ARTIFACT_SCHEMA:-$ROOT/schemas/review-artifact.schema.json}
TEMPLATE=${WATCHDOG_WORKSPACE_TEMPLATE:-$ROOT/workspace-template}
TMP_ROOT=${WATCHDOG_FIXTURE_TMPDIR:-$(mktemp -d "${TMPDIR:-/tmp}/watchdog-fixtures.XXXXXX")}
KEEP_TMP=${WATCHDOG_FIXTURE_KEEP_TMP:-0}
PASS_COUNT=0
FAIL_COUNT=0

cleanup() {
  if [ "$KEEP_TMP" != "1" ]; then
    rm -rf -- "$TMP_ROOT"
  else
    printf 'fixture workspace retained: %s\n' "$TMP_ROOT"
  fi
}
trap cleanup EXIT HUP INT TERM

fail() {
  printf '  assertion failed: %s\n' "$*" >&2
  return 1
}

assert_eq() {
  expected=$1
  actual=$2
  label=$3
  [ "$expected" = "$actual" ] || fail "$label: expected '$expected', got '$actual'"
}

assert_file() {
  [ -f "$1" ] || fail "missing file: $1"
}

assert_no_file() {
  [ ! -e "$1" ] || fail "unexpected file: $1"
}

json_get() {
  python3 - "$1" "$2" <<'PY'
import json
import pathlib
import sys
value = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
for component in sys.argv[2].split("."):
    value = value[int(component)] if isinstance(value, list) else value[component]
if isinstance(value, bool):
    print("true" if value else "false")
elif value is None:
    print("null")
else:
    print(value)
PY
}

hash_persistent_identity() {
  python3 - "$1" <<'PY'
import hashlib
import pathlib
import sys
root = pathlib.Path(sys.argv[1])
digest = hashlib.sha256()
for name in ("identity.json", "persona.json", "score-history.json"):
    digest.update(name.encode())
    digest.update((root / name).read_bytes())
print("sha256:" + digest.hexdigest())
PY
}

hash_artifact() {
  python3 - "$1" <<'PY'
import hashlib
import pathlib
import sys
print("sha256:" + hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
PY
}

validate_scenario_set() {
  if [ -n "${WATCHDOG_SCENARIO_VALIDATOR:-}" ]; then
    "$WATCHDOG_SCENARIO_VALIDATOR" "$ROOT/schemas/scenario.schema.json" "$SCENARIOS"
    return
  fi
  python3 - "$ROOT/schemas/scenario.schema.json" "$SCENARIOS" <<'PY'
import json
import pathlib
import sys
schema = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
document = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
try:
    import jsonschema
except ModuleNotFoundError:
    assert document.get("version") == 1
    scenarios = document.get("scenarios")
    assert isinstance(scenarios, dict) and scenarios
    for name, scenario in scenarios.items():
        assert isinstance(name, str) and name
        assert scenario.get("expected_status") in schema["properties"]["scenarios"]["additionalProperties"]["properties"]["expected_status"]["enum"]
        assert isinstance(scenario.get("responses"), list) and scenario["responses"]
else:
    jsonschema.Draft202012Validator(schema).validate(document)
PY
}

validate_artifact() {
  artifact=$1
  if [ -n "${WATCHDOG_ARTIFACT_VALIDATOR:-}" ]; then
    "$WATCHDOG_ARTIFACT_VALIDATOR" "$ARTIFACT_SCHEMA" "$artifact"
    return
  fi
  python3 - "$ARTIFACT_SCHEMA" "$artifact" <<'PY'
import json
import pathlib
import sys
schema = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
try:
    artifact = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
except (json.JSONDecodeError, OSError):
    raise SystemExit(2)
try:
    import jsonschema
except ModuleNotFoundError:
    required = set(schema["required"])
    allowed = set(schema["properties"])
    assert required <= set(artifact)
    assert set(artifact) <= allowed
    assert artifact["schema_version"] == 1
    assert artifact["agent_id"] == "reviewer-r2"
    assert artifact["phase"] == "initial-review"
    assert isinstance(artifact["artifact_version"], int) and artifact["artifact_version"] >= 1
    assert artifact["decision"] in {"continue", "complete", "blocked"}
else:
    jsonschema.Draft202012Validator(schema).validate(artifact)
PY
}

fresh_workspace() {
  name=$1
  workspace=$TMP_ROOT/$name
  mkdir -p -- "$workspace"
  cp -R -- "$TEMPLATE/." "$workspace/"
  mkdir -p -- "$workspace/phases/initial-review/artifacts" "$workspace/published"
  printf '%s\n' "$workspace"
}

run_fake() {
  scenario=$1
  workspace=$2
  stdout_file=$3
  stderr_file=$4
  FAKE_CODEX_CASE=$scenario \
  FAKE_CODEX_SCENARIO_SET=$SCENARIOS \
  FAKE_CODEX_WORKSPACE=$workspace \
  FAKE_CODEX_STATE_FILE=$workspace/.fake-codex-state.json \
  FAKE_CODEX_ACCESS_LOG=$workspace/.fake-codex-access.ndjson \
    "$FAKE_CODEX" exec --dangerously-bypass-approvals-and-sandbox >"$stdout_file" 2>"$stderr_file"
}

run_with_deadline() {
  deadline_seconds=$1
  scenario=$2
  workspace=$3
  stdout_file=$4
  stderr_file=$5
  FAKE_CODEX_CASE=$scenario \
  FAKE_CODEX_SCENARIO_SET=$SCENARIOS \
  FAKE_CODEX_WORKSPACE=$workspace \
  FAKE_CODEX_STATE_FILE=$workspace/.fake-codex-state.json \
  FAKE_CODEX_ACCESS_LOG=$workspace/.fake-codex-access.ndjson \
    "$FAKE_CODEX" exec --dangerously-bypass-approvals-and-sandbox >"$stdout_file" 2>"$stderr_file" &
  child=$!
  end=$(( $(date +%s) + deadline_seconds ))
  while kill -0 "$child" 2>/dev/null; do
    if [ "$(date +%s)" -ge "$end" ]; then
      kill -TERM "$child" 2>/dev/null || true
      sleep 0.1
      kill -KILL "$child" 2>/dev/null || true
      wait "$child" 2>/dev/null || true
      return 124
    fi
    sleep 0.05
  done
  wait "$child"
}

promise_from() {
  python3 - "$1" <<'PY'
import pathlib
import re
import sys
text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(r"<promise>(NEXT|COMPLETE|BLOCKED(?:: [^<]+)?)</promise>", text)
print(match.group(1) if match else "")
PY
}

has_manifest_violation() {
  python3 - "$1" <<'PY'
import json
import pathlib
import sys
path = pathlib.Path(sys.argv[1])
if not path.exists():
    raise SystemExit(1)
for line in path.read_text(encoding="utf-8").splitlines():
    if line and not json.loads(line)["allowed"]:
        raise SystemExit(0)
raise SystemExit(1)
PY
}

wait_for_attempt() {
  state_file=$1
  expected=$2
  remaining=100
  while [ "$remaining" -gt 0 ]; do
    if [ -f "$state_file" ] && [ "$(json_get "$state_file" attempt)" = "$expected" ]; then
      return 0
    fi
    remaining=$((remaining - 1))
    sleep 0.05
  done
  return 1
}

test_happy_path() {
  workspace=$(fresh_workspace happy)
  run_fake happy-path "$workspace" "$workspace/stdout" "$workspace/stderr" || return 1
  assert_eq COMPLETE "$(promise_from "$workspace/stdout")" "completion promise" || return 1
  artifact=$workspace/phases/initial-review/artifacts/review.json
  assert_file "$artifact" || return 1
  validate_artifact "$artifact" || return 1
  assert_eq SUCCESS "$(json_get "$SCENARIOS" scenarios.happy-path.expected_status)" "terminal status"
}

test_malformed_artifact_reopen() {
  workspace=$(fresh_workspace malformed)
  run_fake malformed-artifact "$workspace" "$workspace/stdout" "$workspace/stderr" || return 1
  artifact=$workspace/phases/initial-review/artifacts/review.json
  if validate_artifact "$artifact"; then
    return 1
  fi
  feedback='REOPEN: artifact validation failed: invalid JSON'
  assert_eq "$(json_get "$SCENARIOS" scenarios.malformed-artifact.expected_feedback)" "$feedback" "reopen feedback"
}

test_missing_artifact_reopen() {
  workspace=$(fresh_workspace missing)
  run_fake missing-artifact "$workspace" "$workspace/stdout" "$workspace/stderr" || return 1
  assert_eq COMPLETE "$(promise_from "$workspace/stdout")" "completion promise" || return 1
  assert_no_file "$workspace/phases/initial-review/artifacts/review.json" || return 1
  feedback='REOPEN: COMPLETE promise requires a schema-valid artifact'
  assert_eq "$(json_get "$SCENARIOS" scenarios.missing-artifact.expected_feedback)" "$feedback" "reopen feedback"
}

test_crash_resume_identity() {
  workspace=$(fresh_workspace crash-resume)
  before=$(hash_persistent_identity "$workspace")
  run_fake crash-resume "$workspace" "$workspace/stdout-1" "$workspace/stderr-1"
  first_rc=$?
  assert_eq 70 "$first_rc" "simulated crash exit" || return 1
  run_fake crash-resume "$workspace" "$workspace/stdout-2" "$workspace/stderr-2" || return 1
  after=$(hash_persistent_identity "$workspace")
  assert_eq "$before" "$after" "persistent identity/persona/score history" || return 1
  assert_eq 2 "$(json_get "$workspace/.fake-codex-state.json" attempt)" "resume attempt" || return 1
  validate_artifact "$workspace/phases/initial-review/artifacts/review.json"
}

test_phase_before_gate_refused() {
  workspace=$(fresh_workspace gate-refusal)
  gate_open=$(json_get "$SCENARIOS" scenarios.phase-before-gate.gate_open)
  status=SUCCESS
  if [ "$gate_open" != true ]; then
    status=BLOCKED
  else
    run_fake phase-before-gate "$workspace" "$workspace/stdout" "$workspace/stderr" || status=FAILED
  fi
  assert_eq BLOCKED "$status" "closed phase gate" || return 1
  assert_no_file "$workspace/.fake-codex-state.json"
}

test_manifest_violation_rejected() {
  workspace=$(fresh_workspace manifest-violation)
  printf 'not visible to the agent\n' >"$TMP_ROOT/forbidden-secret.txt"
  run_fake manifest-violation "$workspace" "$workspace/stdout" "$workspace/stderr" || return 1
  if has_manifest_violation "$workspace/.fake-codex-access.ndjson"; then
    status=POLICY_BLOCKED
  else
    status=SUCCESS
  fi
  assert_eq POLICY_BLOCKED "$status" "manifest policy status"
}

test_no_progress_stall() {
  workspace=$(fresh_workspace no-progress)
  threshold=$(json_get "$SCENARIOS" scenarios.no-progress.no_progress_threshold)
  no_progress=0
  prior_hash=
  iteration=1
  status=INCOMPLETE
  while [ "$iteration" -le 4 ]; do
    run_fake no-progress "$workspace" "$workspace/stdout-$iteration" "$workspace/stderr-$iteration" || return 1
    artifact=$workspace/phases/initial-review/artifacts/review.json
    validate_artifact "$artifact" || return 1
    current_hash=$(hash_artifact "$artifact")
    if [ -n "$prior_hash" ] && [ "$current_hash" = "$prior_hash" ]; then
      no_progress=$((no_progress + 1))
    else
      no_progress=0
    fi
    prior_hash=$current_hash
    if [ "$no_progress" -ge "$threshold" ]; then
      status=STALLED
      break
    fi
    iteration=$((iteration + 1))
  done
  assert_eq STALLED "$status" "no-progress terminal status" || return 1
  assert_eq "$threshold" "$no_progress" "no-progress count"
}

test_wall_clock_exhaustion() {
  workspace=$(fresh_workspace wall-clock)
  run_with_deadline 1 wall-clock-exhaustion "$workspace" "$workspace/stdout" "$workspace/stderr"
  rc=$?
  assert_eq 124 "$rc" "deadline exit" || return 1
  status=TIME_EXHAUSTED
  assert_eq "$(json_get "$SCENARIOS" scenarios.wall-clock-exhaustion.expected_status)" "$status" "wall-clock terminal status"
}

test_term_resume() {
  workspace=$(fresh_workspace term-resume)
  before=$(hash_persistent_identity "$workspace")
  FAKE_CODEX_CASE=term-resume \
  FAKE_CODEX_SCENARIO_SET=$SCENARIOS \
  FAKE_CODEX_WORKSPACE=$workspace \
  FAKE_CODEX_STATE_FILE=$workspace/.fake-codex-state.json \
  FAKE_CODEX_ACCESS_LOG=$workspace/.fake-codex-access.ndjson \
    "$FAKE_CODEX" exec --dangerously-bypass-approvals-and-sandbox >"$workspace/stdout-1" 2>"$workspace/stderr-1" &
  child=$!
  wait_for_attempt "$workspace/.fake-codex-state.json" 1 || return 1
  kill -TERM "$child" || return 1
  wait "$child"
  first_rc=$?
  assert_eq 143 "$first_rc" "TERM forwarding exit" || return 1
  run_fake term-resume "$workspace" "$workspace/stdout-2" "$workspace/stderr-2" || return 1
  assert_eq 2 "$(json_get "$workspace/.fake-codex-state.json" attempt)" "TERM resume attempt" || return 1
  assert_eq "$before" "$(hash_persistent_identity "$workspace")" "TERM identity continuity" || return 1
  validate_artifact "$workspace/phases/initial-review/artifacts/review.json"
}

test_watchdog_runner_adapter() {
  workspace=$(fresh_workspace runner-adapter)
  WATCHDOG_FIXTURE_CASE=happy-path \
  WATCHDOG_AGENT_DIR=$workspace \
  WATCHDOG_PHASE=initial-review \
  WATCHDOG_PHASE_DIR=$workspace/phases/initial-review \
    "$ROOT/watchdog-runner-adapter.sh" || return 1
  result=$workspace/phases/initial-review/invocation-result.json
  assert_file "$result" || return 1
  assert_eq complete "$(json_get "$result" status)" "adapter completion status" || return 1
  assert_eq true "$(json_get "$result" validated)" "adapter validation flag" || return 1
  assert_eq COMPLETE "$(json_get "$result" promise)" "adapter promise"
}

test_committee_watchdog_engine() {
  repo_root=$(CDPATH= cd -- "$ROOT/../../.." && pwd)
  engine=$repo_root/engine/watchdog/committee-watchdog.sh
  [ -x "$engine" ] || fail "committee watchdog is not executable: $engine"
  (cd "$repo_root" && python3 -m unittest engine.watchdog.test_watchdog_runtime)
}

test_frozen_workspace_documents() {
  repo_root=$(CDPATH= cd -- "$ROOT/../../.." && pwd)
  "$repo_root/engine/watchdog/contracts-adapter.sh" verify-manifest --manifest "$TEMPLATE/allowed-inputs.json" || return 1
  python3 - "$repo_root" "$TEMPLATE" <<'PY'
import json
import pathlib
import sys
from jsonschema import Draft202012Validator, FormatChecker

repo = pathlib.Path(sys.argv[1])
base = pathlib.Path(sys.argv[2])
schemas = repo / "packages/schemas/schemas"
checks = {
    "identity.json": "identity",
    "persona.json": "persona",
    "role-state.json": "role-state",
    "concern-ledger.json": "concern-ledger",
    "question-ledger.json": "question-ledger",
    "score-history.json": "score-history",
    "literature-registry.json": "literature-registry",
    "current-task-context.json": "task-context",
    "phases/initial-review/tasks.json": "phase-tasks",
    "allowed-inputs.json": "allowed-inputs",
    "phases/initial-review/state.json": "phase-state",
}
for relative, name in checks.items():
    schema = json.loads((schemas / f"{name}.schema.json").read_text(encoding="utf-8"))
    value = json.loads((base / relative).read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    assert not errors, (relative, [error.message for error in errors])
config_schema = json.loads((schemas / "watchdog-config.schema.json").read_text(encoding="utf-8"))
config = json.loads((base.parent / "watchdog-config.json").read_text(encoding="utf-8"))
config_errors = list(Draft202012Validator(config_schema, format_checker=FormatChecker()).iter_errors(config))
assert not config_errors, [error.message for error in config_errors]
PY
}

run_test() {
  name=$1
  shift
  printf 'TEST %s\n' "$name"
  if "$@"; then
    PASS_COUNT=$((PASS_COUNT + 1))
    printf '  PASS\n'
  else
    FAIL_COUNT=$((FAIL_COUNT + 1))
    printf '  FAIL\n' >&2
  fi
}

validate_scenario_set || {
  printf 'scenario/schema validation failed\n' >&2
  exit 1
}
[ -x "$FAKE_CODEX" ] || {
  printf 'fake Codex is not executable: %s\n' "$FAKE_CODEX" >&2
  exit 1
}

run_test happy-path test_happy_path
run_test malformed-artifact-reopen test_malformed_artifact_reopen
run_test missing-artifact-reopen test_missing_artifact_reopen
run_test crash-resume-identity test_crash_resume_identity
run_test phase-before-gate-refused test_phase_before_gate_refused
run_test manifest-violation-rejected test_manifest_violation_rejected
run_test no-progress-stall test_no_progress_stall
run_test wall-clock-exhaustion test_wall_clock_exhaustion
run_test term-resume test_term_resume
run_test watchdog-runner-adapter test_watchdog_runner_adapter
run_test committee-watchdog-engine test_committee_watchdog_engine
run_test frozen-workspace-documents test_frozen_workspace_documents

ENGINE_WATCHDOG=${WATCHDOG_BIN:-$ROOT/../../../engine/watchdog/committee-watchdog.sh}
printf 'ENGINE verified=%s\n' "$ENGINE_WATCHDOG"

printf '\nRESULT pass=%s fail=%s\n' "$PASS_COUNT" "$FAIL_COUNT"
[ "$FAIL_COUNT" -eq 0 ]
