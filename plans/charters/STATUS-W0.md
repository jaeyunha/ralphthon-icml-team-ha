# W0 A-CONTRACTS Status

## State

**DONE — CONTRACTS FROZEN**

`packages/schemas/` is the JSON Schema draft 2020-12 source of truth. `packages/contracts/` and all golden fixtures are aligned to those schemas. Downstream lanes must not edit either package directly; proposed changes go through `plans/schema-change-requests/` and are applied only by the INTEGRATE lane.

## Delivered

- Bun workspace and root lockfile; uv workspace for `engine/extraction` and `engine/validators`.
- 27 artifact schemas, deterministic generated TypeScript types, AJV tests, and Python `jsonschema` tests.
- §19.2 run state machine and terminal failure states.
- Persistent-role phase machines and all R2.10 entry/completion gates.
- §26 quality predicates.
- R2.11 table-driven visibility manifests, invariant prompt inputs, canonical manifest hashing, and actor-matched R2.13 event naming.
- Atomic validated writes, immutable publication without replacement, run leases, guarded event sequences, and SHA-256 freeze creation/verification.
- Append-only, prior-hash-linked score-history update validation.
- Shared agent policy and ICML 2026 review rubric.
- `scripts/validate-run.sh` with schema validation, manifest hash checking, event uniqueness checking, fixture coverage, and mutation detection.
- One valid and one invalid golden fixture for every schema under `tests/fixtures/contracts/`.

## Clean-checkout verification

Verified from detached clean worktree at commit `8603389`:

- `bun install --frozen-lockfile` — passed.
- `bun run generate:types` followed by generated-file diff check — no drift.
- `bun run --cwd packages/schemas check:types` — passed.
- `bun run --cwd packages/contracts check` — 39 tests passed; TypeScript check passed.
- `bun test` — 63 tests passed.
- `scripts/validate-run.sh tests/fixtures/contracts/sample-run` — 27 documents validated.
- `scripts/validate-run.sh --check-fixtures tests/fixtures/contracts` — 27 valid fixtures, 27 invalid fixtures, mutation detected.
- `uv sync --frozen && uv run --frozen pytest` — 54 tests passed.

## Integration notes

- One logical `identity` artifact represents each persistent agent; `phase-state` represents separate phase executions.
- Official review v1 and final review use immutable version contracts; `atomicPublishJson` prevents replacement of an existing published artifact.
- Decision contracts support both `single_paper` and `batch` outcomes, including `accept_regular` and `accept_spotlight`.
- Event storage must enforce `UNIQUE(run_id, sequence)` and globally unique `event_id`; the validator checks both within run artifacts.
