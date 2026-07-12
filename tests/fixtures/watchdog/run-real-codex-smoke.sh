#!/usr/bin/env bash
set -euo pipefail

FIXTURE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$FIXTURE_DIR/../../.." && pwd)
AGENT_LOOP="$REPO_ROOT/engine/loops/agent-loop.sh"
CONTRACT_ADAPTER="$REPO_ROOT/engine/watchdog/contracts-adapter.sh"
command -v codex >/dev/null 2>&1 || {
  printf 'real smoke: codex CLI is required\n' >&2
  exit 127
}

TMP_ROOT=${WATCHDOG_REAL_SMOKE_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/watchdog-codex-smoke.XXXXXX")}
KEEP_TMP=${WATCHDOG_REAL_SMOKE_KEEP_TMP:-0}
cleanup() {
  if [ "$KEEP_TMP" = "1" ]; then
    printf 'real smoke workspace retained: %s\n' "$TMP_ROOT"
  else
    rm -rf -- "$TMP_ROOT"
  fi
}
trap cleanup EXIT HUP INT TERM

DESIGN_ROOT="$TMP_ROOT/design"
RUN_ROOT="$TMP_ROOT/run-hello"
WORKSPACE="$RUN_ROOT/agents/reviewer-smoke"
PHASE_DIR="$WORKSPACE/phases/initial-review"
ARTIFACT="$PHASE_DIR/artifacts/hello.json"
mkdir -p "$DESIGN_ROOT/shared" "$DESIGN_ROOT/roles/reviewer/phases/initial-review" "$DESIGN_ROOT/roles/reviewer/schemas" "$PHASE_DIR/artifacts"
cp "$REPO_ROOT/shared/COMMON_AGENT_POLICY.md" "$DESIGN_ROOT/shared/COMMON_AGENT_POLICY.md"
cp "$REPO_ROOT/shared/ICML_2026_REVIEW_RUBRIC.md" "$DESIGN_ROOT/shared/ICML_2026_REVIEW_RUBRIC.md"

python3 - "$DESIGN_ROOT" "$WORKSPACE" "$PHASE_DIR" <<'PY'
import json
import pathlib
import sys

design = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
phase = pathlib.Path(sys.argv[3])
(design / "roles/reviewer/PROMPT.base.md").write_text(
    "You are a smoke-test reviewer. Perform only the supplied trivial task.\n",
    encoding="utf-8",
)
(design / "roles/reviewer/phases/initial-review/PROMPT.md").write_text(
    "Write the requested hello artifact exactly as the schema requires, then stop.\n",
    encoding="utf-8",
)
(design / "roles/reviewer/schemas/initial-review.schema.json").write_text(
    json.dumps({
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["message"],
        "properties": {"message": {"const": "hello"}},
    }),
    encoding="utf-8",
)
workspace.mkdir(parents=True, exist_ok=True)
(workspace / "persona.json").write_text(json.dumps({
    "persona_version": 1,
    "reviewer_id": "reviewer-smoke",
    "primary_expertise": ["smoke testing"],
    "secondary_expertise": [],
    "familiarity": {},
    "likely_deep_dive_areas": [],
    "known_blind_spots": [],
    "confidence_policy": "Report only observed smoke-test output",
    "decision_bias": "neutral",
    "communication_style": "concise",
}), encoding="utf-8")
(phase / "current-task-context.json").write_text(json.dumps({
    "task_id": "write-hello",
    "task": "Write hello.json containing exactly {\"message\": \"hello\"}",
    "completion_predicate": "The artifact validates against the supplied schema",
}), encoding="utf-8")
PY

"$AGENT_LOOP" \
  --repo-root "$DESIGN_ROOT" \
  --agent-id reviewer-smoke \
  --role reviewer \
  --phase initial-review \
  --workspace "$WORKSPACE" \
  --task-context "$PHASE_DIR/current-task-context.json" \
  --output-schema "$DESIGN_ROOT/roles/reviewer/schemas/initial-review.schema.json" \
  --artifact "$ARTIFACT" \
  --manifest-generator "$CONTRACT_ADAPTER" \
  --timeout "${WATCHDOG_REAL_SMOKE_TIMEOUT:-300}"

python3 - "$ARTIFACT" "$PHASE_DIR/invocation-result.json" "$WORKSPACE/allowed-inputs.json" <<'PY'
import json
import pathlib
import sys

artifact = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
result = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
manifest = json.loads(pathlib.Path(sys.argv[3]).read_text(encoding="utf-8"))
assert artifact == {"message": "hello"}, artifact
assert result["status"] == "settled", result
assert result["promise"] in {"NEXT", "COMPLETE"}, result
assert result["allowed_input_manifest_hash"] == manifest["manifest_hash"], (result, manifest)
print(f"REAL_CODEX_SMOKE PASS promise={result['promise']} artifact_hash={result['artifact_hash']}")
PY
