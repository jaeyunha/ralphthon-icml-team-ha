# STATUS W2 G3-STATREF

## State

Done in Lane G3.

## Implemented

- Persistent logical validator role modules with phase-specific Ralph loops:
  - `roles/validators/statistics/`
  - `roles/validators/references/`
  - `roles/validators/ethics/`
  - `roles/validators/arbitration/`
- Hashed phase input manifests and stable identity/state handling in `engine/validators/arbitration/lifecycle.py`, using the approved role names `validator_statistics`, `validator_references`, `validator_ethics`, and `validator_arbitration` from integrated-main commit `8ce2eec`.
- Dossier-driven validation planner for code, mathematics, statistics, references, and ethics targets.
- Statistical audit covering runs, seeds, uncertainty, multiplicity, leakage, split integrity, baseline/tuning/metric fairness, claim/evidence breadth, and recorded robustness axes.
- Reference validation covering conservative extraction, broker request generation, identity statuses, citation-support statuses, publication status, challenge rechecks, and typed refusal handling. A broker refusal alone never becomes `confirmed_nonexistent`.
- Evidence-only ethics/integrity trigger assessment with review flags and a permanently null misconduct determination.
- Cross-lane arbitration that validates every frozen finding, rejects duplicate IDs and under-confirmed high-impact findings, surfaces conflicts without averaging, validates a role-local bundle schema, and freezes a canonical SHA-256 content hash.

## Done-when evidence

### Planted defects

`uv run pytest engine/validators -q`

Result: `10 passed`.

The suite proves:

- exact train/held-out identifier leakage is caught and independently confirmed;
- unfair compute, tuning, split, and metric baseline treatment is caught;
- a planted nonexistent reference is `confirmed_nonexistent` only with broker plus two independent registry checks;
- a planted misquotation is classified `source_never_makes_claim` with two confirmation paths;
- PII and prompt-injection triggers produce a required ethics-review flag without a misconduct claim;
- persistent identity survives phase changes and manifest visibility rejects unlisted review input;
- G1/G2-shaped frozen findings arbitrate into one conflict-preserving bundle.

### Real paper 34584 bibliography

The controlled literature broker processed all 32 bibliography entries from the frozen M1 dossier with the historical cutoff and Ever enabled:

```text
{"processed":32,"responses":12,"refusals":20}
{"validated":32,"findings":32}
```

Committed evidence:

- `tests/fixtures/validators-statref/real-34584-broker/processed/literature/` — all 32 broker requests;
- `tests/fixtures/validators-statref/real-34584-broker/inbox/literature/` — 12 evidence responses and 20 typed refusals;
- `tests/fixtures/validators-statref/real-34584-runs/run-34584-g3-real/agents/validator-references/literature-broker/query-provenance.ndjson` — privacy-preserving broker provenance;
- `tests/fixtures/validators-statref/real-34584-reference-report.json` — 32 anchored, frozen-schema-valid identity findings.

Typed refusals and low-similarity candidates remain `unresolved` or `likely_nonexistent`; the real run does not silently convert lookup failure into confirmed nonexistence.

### Frozen arbitration fixture

`tests/fixtures/validators-statref/frozen-validation-bundle.json` contains 43 schema-valid findings from representative G1 code, G2 mathematics, G3 statistics, real references, and ethics lanes. It preserves one explicit code/math conflict as `surfaced_not_averaged`.

Content hash:

```text
sha256:09b36fa446f0f5843358f5150fe3138124acc3b4ae4c87fc2d7804a74d55b8a0
```

### Repository verification

- `uv run pytest -q` → `103 passed`.
- `bun install --frozen-lockfile && bun test` → `130 pass`, `8 skip`, `0 fail`.
- `uv run ruff check engine/validators` → all checks passed.

## Integration notes

- Frozen `packages/contracts` and `packages/schemas` were not edited by this lane.
- Validator allowed-input role approval already exists on integrated main at `8ce2eec`; this lane's manifest structure matches that approved contract.
- `plans/schema-change-requests/003-validation-bundle.md` requests promotion of the role-local arbitration wrapper schema into the shared frozen schema set. Individual bundle findings already validate against the frozen W0 `validation-finding` schema.
- The committed G1/G2 inputs are contract-shaped fixtures. INTEGRATE can replace them with the final Lane G1/G2 fixture paths without changing arbitration code.

## Remaining

No Lane G3 implementation work remains. INTEGRATE owns shared-schema promotion and replacement of representative G1/G2 fixtures with the final lane artifacts.
