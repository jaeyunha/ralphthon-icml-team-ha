# STATUS-WATCHDOG-RUNTIME — Operational watchdog schemas

## Result

COMPLETE on `integrate/schema-001-extraction`.

The authorized W1-D watchdog runtime schema request is implemented compatibly with the completed extraction schema request and the frozen contract infrastructure.

## Delivered

- Added seven strict draft 2020-12 operational schemas:
  - `watchdog-status.schema.json`
  - `run-budget.schema.json`
  - `invocation-result.schema.json`
  - `phase-tasks.schema.json`
  - `task-context.schema.json`
  - `watchdog-config.schema.json`
  - `literature-registry.schema.json`
- Amended `phase-state.schema.json` to permit honest pre-invocation/pre-artifact state:
  - `attempt: 0` and optional `attempt_count: 0`;
  - `last_artifact_hash: null`;
  - optional reason, failure/reopen category, promise, PID, eligibility, and update fields.
- Amended `score-history.schema.json` to permit `entries: []` while preserving strict entry shapes, score ranges, append-only semantics, and hash requirements for populated entries.
- Registered the seven schemas and regenerated TypeScript declarations.
- Extended the type generator to resolve cross-schema `$ref` declarations to concrete generated TypeScript types.
- Added one valid and one invalid contract fixture for every new schema.
- Added boundary coverage for phase-state zero/null values and empty score history.
- Added a minimal no-manifest watchdog run tree under `tests/fixtures/contracts/watchdog-run/`.
- Added path-aware validator inference for:
  - `.watchdog/status.json`;
  - `.watchdog/run-budget.json`;
  - root `watchdog-config.json`;
  - `agents/<id>/literature-registry.json`;
  - `agents/<id>/phases/<phase>/state.json`;
  - phase `tasks.json`, `current-task-context.json`, and `invocation-result.json`.
- Added regression tests proving unrelated generic `status.json`, `state.json`, and `tasks.json` files are not silently misclassified.
- Preserved control-manifest SHA-256 checks, strict schemas, invalid-fixture coverage, mutation detection, and extraction fixture inference.

## Compatibility evidence

A focused Python/jsonschema check validated six existing W1-D lane documents directly against the integrated schemas:

- `watchdog-config.json`;
- phase `tasks.json`;
- `current-task-context.json`;
- `literature-registry.json`;
- phase `state.json`;
- populated `score-history.json`.

Result: `validated 6 W1-D fixture documents against integrated schemas`.

## Final verification evidence

| Check | Result |
|---|---|
| `bun run generate:types && git diff --exit-code -- packages/schemas/generated/index.ts && bun run --cwd packages/schemas check:types` | PASS — no generated-type drift |
| `bun run --cwd packages/schemas test` | PASS — 27 tests, 173 expectations |
| `bun run --cwd packages/contracts check` | PASS — 39 tests, 136 expectations; TypeScript check passed |
| `bun test` | PASS — 66 tests, 309 expectations |
| `uv run --frozen pytest -q` | PASS — 93 tests |
| `scripts/validate-run.sh --check-fixtures tests/fixtures/contracts` | PASS — 40 valid documents, 40 invalid fixtures, mutation detected |
| `scripts/validate-run.sh tests/fixtures/contracts/watchdog-run` | PASS — 7 documents validated without a control manifest |
| `scripts/validate-run.sh tests/fixtures/extraction/34584` | PASS — 6 extraction documents remain valid |
| `git diff --check` | PASS |

## Team execution evidence

Team `implement-the-authorized-w1-d-8466bd0e` completed all three lanes:

- operational schemas and compatible amendments;
- path-aware validator inference and run-tree compatibility;
- fixtures and regression tests.

Terminal state was verified as `phase=complete`, with `pending=0`, `in_progress=0`, `failed=0`, `completed=3`, and workers 1–3 gracefully stopped.
