# Charter W0 A-CONTRACTS — scaffold, contracts, state machine

Spec: V2 §8 (freeze), §19.2 (state machine), §25 (data contracts), §26
(gates), §28.A, plus PHASED_ROLE_ARCHITECTURE R2.9 (role/phase state),
R2.10 (transition gates), R2.11 (visibility matrix), R2.14 (DB). Serial
prerequisite for every other lane.

## Owns
Repo root scaffold, `packages/contracts/`, `packages/schemas/`, `shared/`
(COMMON_AGENT_POLICY.md, ICML_2026_REVIEW_RUBRIC.md), `scripts/validate-run.sh`,
`tests/fixtures/contracts/`.

## Deliverables
1. Bun workspace scaffold: root `package.json` (workspaces), `bunfig.toml`,
   `apps/`, `engine/`, `packages/`, `roles/`, `shared/`, `scripts/`,
   `runs/` (gitignored), `migrations/`, `tests/`. Python side: root
   `pyproject.toml` (uv) for `engine/extraction` + `engine/validators`.
2. `packages/schemas/`: JSON Schema files (draft 2020-12) for every artifact
   in spec §25 + §8.2 + §19.4 + R2.9: run-config, submission-manifest,
   freeze-record, run-state, event envelope + §22.3 event types with
   phase-qualified names (R2.13), **role-state and phase-state (R2.9),
   allowed-inputs manifest, concern-ledger, question-ledger, score-history
   (append-only), identity**, paper-dossier + claim, persona,
   evidence-packet, validation-finding (all §12 status enums),
   official-review (immutable versioned), followup, discussion-position,
   final-review, rebuttal response-matrix, concern-resolution,
   discussion-issue, meta-review, decision. JSON Schema is the single
   source; TS types generated, Python validates with jsonschema.
3. `packages/contracts/` (TS): run state machine (§19.2 + failure states),
   **role phase machines with R2.10 transition gates** (reviewer:
   initial-review → followup → discussion → final-justification; author:
   rebuttal → final-followup; ac: reviewer-coverage → review-quality-check
   → discussion-moderation → meta-review; sac: calibration; pc:
   finalization), §26 gate predicates, **allowed-inputs manifest generator
   + hasher implementing the R2.11 visibility matrix**, atomic write helper
   (tmp → validate → rename), run lock/lease, event sequence allocator,
   SHA-256 freeze hashing.
4. `scripts/validate-run.sh`: walks a `runs/<id>/` tree and validates every
   artifact against its schema.
5. Golden fixtures: one minimal valid + one invalid instance per schema in
   `tests/fixtures/contracts/`.

## Rules
- Score ranges exactly per §13.5 (sub-scores 1–4, overall 1–6, confidence 1–5).
- Event table contract: `UNIQUE(run_id, sequence)` semantics encoded in the
  envelope schema (§22.3).
- Decision artifact supports single-paper and batch modes (§18).
- One logical `agents` identity per role instance; phase executions are
  `agent_phase_runs` rows (R2.14). Encode this split in the schemas.
- Score-history schema is append-only: an update without the prior entries
  intact must fail validation.
- Immutable versions: official-review v1 and final-review are frozen
  artifacts; later phases reference, never mutate.

## Done when
- `bun install && bun test` green in `packages/contracts`.
- `bun run generate:types` produces TS types from schemas with no drift.
- `scripts/validate-run.sh tests/fixtures/contracts/sample-run` passes;
  mutating any artifact makes it fail.
- Every §25 example in the spec and every R2.9 state example validates
  against its schema verbatim.
- Visibility-matrix tests: generated manifests for each role/phase match
  R2.11 exactly (table-driven).
- STATUS.md written; contracts declared FROZEN.
