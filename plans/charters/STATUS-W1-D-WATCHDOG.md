# W1-D-WATCHDOG Status

## State

**DONE — merged runtime contracts adopted and all charter gates pass**

Rebased onto current local `main` at `91d521f` (`merge: W1 controlled literature broker with Ever`), which includes the approved watchdog schemas, W1-J database/projector work, extraction integration, and broker integration. Root `bun install` completed with no lockfile changes. No lane changes were made to `packages/contracts/`, `packages/schemas/`, `packages/db/`, `engine/projector/`, or `bun.lock`.

## Delivered

- `engine/loops/agent-loop.sh`
  - one coherent work item per invocation;
  - W0 allowed-input manifest generation, verification, and canonical hashing;
  - R2.12 prompt composition with common policy and rubric and no PRD injection;
  - workspace cwd, run-root-relative manifest paths, heartbeat, timeout, and signal forwarding;
  - exact `NEXT`, `COMPLETE`, and `BLOCKED` promise handling;
  - schema-qualified atomic `invocation-result.json`, exact reopen feedback, and policy rejection.
- `engine/watchdog/committee-watchdog.sh` and `watchdog_runtime.py`
  - durable lock, status, budget, task queue, restart, subscription cursor, and event state;
  - persistent logical identity with nested phase workspaces;
  - legal persistent-role phase ordering and W0-derived phase-entry gates;
  - W0-checked one-step run-state transitions;
  - per-agent restart/reap with capped exponential backoff;
  - validated-artifact no-progress detection, heartbeat enforcement, wall-clock/cost/discussion ceilings, and honest terminal statuses;
  - TERM/INT forwarding and clean resume with the same identity;
  - approved `watchdog-status`, `run-budget`, `watchdog-config`, `phase-state`, `phase-tasks`, `task-context`, `invocation-result`, `score-history`, and `literature-registry` documents;
  - honest pre-invocation `attempt: 0`, `attempt_count: 0`, and `last_artifact_hash: null`;
  - empty reviewer score history and literature registry initialization without fabricated scientific state;
  - task context and queue attempt/status synchronization across start, retry, block, and completion;
  - no `state.runtime` sidecars and no zero-SHA artifact sentinel.
- `engine/watchdog/contracts-adapter.{sh,ts}`
  - W0 `generateAllowedInputsManifest` and canonical verification;
  - W0 phase-entry gate evaluation and run-transition checks;
  - W0 atomic manifest writes and rejection of prompt inputs outside the frozen visibility matrix.
- W1-J projector integration
  - watchdog events are emitted through `engine/projector/src/emit-event.ts` and therefore `RunEventEmitter`;
  - event sequence allocation, NDJSON locking, W0 envelope validation, phase-qualified type validation, and append durability use the merged W1-J implementation;
  - tests verify the canonical sequence state shape and exact agreement between its allocated sequence and `events.ndjson`.
- `tests/fixtures/watchdog/`
  - scripted fake Codex, runner adapter, honest zero-attempt/empty-history workspace fixtures, 12-gate integration harness, and reproducible real-Codex smoke harness.

The approved request remains recorded at `plans/schema-change-requests/W1-D-WATCHDOG-RUNTIME.md`; implementation/validator completion is recorded by main at `plans/schema-change-requests/STATUS-WATCHDOG-RUNTIME.md`.

## Charter gate evidence

- `tests/fixtures/watchdog/run-integration.sh` — **PASS**, `RESULT pass=12 fail=0`.
  - Includes happy path, malformed and missing artifact reopen, crash/restart identity continuity, phase-entry refusal, manifest violation, no-progress stall, wall-clock exhaustion, TERM/resume, adapter settlement, 20 watchdog unit/integration tests, legacy sidecar/sentinel migration, and approved runtime fixture validation.
- `python3 -m unittest engine.watchdog.test_watchdog_runtime` — **PASS**, 20 tests.
  - Includes runtime-generated complete run-tree validation through `scripts/validate-run.sh`.
- `tests/fixtures/watchdog/run-real-codex-smoke.sh` — **PASS** with Codex CLI `0.144.1`.
  - Result: `REAL_CODEX_SMOKE PASS promise=COMPLETE artifact_hash=sha256:0cc65ae44a4091b9178ac9c8500153a56517dd3377829103b79cd3c3eec0488b`.
- `scripts/validate-run.sh tests/fixtures/contracts/watchdog-run` — **PASS**, 7 documents without a control manifest.
- `scripts/validate-run.sh --check-fixtures tests/fixtures/contracts` — **PASS**, 40 valid documents, 40 invalid fixtures, and mutation detection.
- Post-rebase `bun install && bun test` — **PASS**, lockfile unchanged; 130 passed, 8 skipped, 0 failed.
- `bun run --cwd packages/contracts check` — **PASS**, 39 tests and TypeScript check.
- `bun run --cwd packages/schemas check:types` — **PASS**, no generated-type drift.
- `bun run --cwd engine/projector typecheck` — **PASS**.
- `bun run --cwd packages/db typecheck` — **PASS**.
- `uv run --frozen pytest -q` — **PASS**, 93 tests.
- `bun build engine/watchdog/contracts-adapter.ts --target=bun` — **PASS**.
- Shell syntax, Python bytecode compilation, and `git diff --check` — **PASS**.

## Integration notes

- Frozen `run-config.json` remains the canonical scientific/run policy document. `watchdog-config.json` is separately materialized and validated as the supervisor execution plan.
- Every durable watchdog operational JSON document now uses an approved merged schema. Generic phase filenames such as `state.json`, `tasks.json`, and `current-task-context.json` are recognized through main's path-aware validator inference.
- The W1-J `RunEventEmitter` owns event sequencing and append behavior. Its internal sequence allocator state is stored at `.watchdog/event-sequence.state`; all durable public events remain W0 `event-envelope` NDJSON in `events.ndjson` and are projector/database compatible.
- The runtime accepts legacy unversioned fake-runner results only for backward-compatible fixture scenarios. Versioned invocation results are validated against the approved `invocation-result` schema before reconciliation.
- Complete watchdog run trees now validate directly with `scripts/validate-run.sh`; no control manifest, synthetic score, zero-hash artifact, or runtime sidecar is required.
