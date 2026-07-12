# Validator artifact schema proposal result

## State

Ready for INTEGRATE review and application. No file under `packages/contracts` or `packages/schemas` was edited.

## Proposed contracts

Seven strict draft-2020-12 schemas:

1. `math-claim-inventory.schema.json`
2. `math-tool-evidence.schema.json`
3. `math-formal-proof-result.schema.json`
4. `math-confirmation-report.schema.json`
5. `math-finding-ledger.schema.json`
6. `math-validation-bundle.schema.json`
7. `validation-bundle.schema.json`

The tool-evidence schema is a closed `oneOf` union for assumption audits, symbolic identities, symbolic gradients, SMT results, shape checks, equation-to-code comparisons, and numerical/counterexample searches. The formal-proof schema remains separate so proof validity and formalization fidelity cannot be conflated.

## Coverage evidence

```text
uv run python plans/schema-change-requests/004-validator-artifact-schema-proposals/validate_proposals.py
```

Passed with:

- 7 proposal schemas structurally valid;
- 7 valid examples accepted;
- 7 invalid examples rejected;
- 73 committed target fixtures covered by exactly one inference rule;
- all 7 proposal schemas exercised by committed fixtures;
- 14 allowed-input manifests, 14 phase states, 14 findings, 12 math tool artifacts, 4 claim inventories, 4 math bundles, 2 proof results, 2 confirmation reports, 2 ledgers, and the finalized G3 bundle validated;
- mathematical bundle/ledger/confirmation/artifact-reference relationships verified;
- G3 conflict references, status agreement, source-lane coverage, and canonical content hash verified.

Additional verification:

- `uv run ruff check plans/schema-change-requests/004-validator-artifact-schema-proposals/validate_proposals.py` — passed.
- `uv run pytest engine/validators/tests -q` — 23 passed.
- `cd engine/validators/math && uv run pytest tests -q` — 6 passed, including real pinned Lean execution.
- `git diff --check` — passed.

## Promotion steps for INTEGRATE

1. Copy the seven schema files into `packages/schemas/schemas/`.
2. Add the canonical filename stems and legacy path aliases from `inference-map.json` to `scripts/validate-run.sh`.
3. Promote valid and invalid examples into shared contract fixtures.
4. Regenerate TypeScript types and run shared schema/type tests.
5. Preserve the semantic checks from `validate_proposals.py` in integration coverage; JSON Schema alone cannot enforce count equality, cross-document ledgers, artifact resolution, conflict references, source-lane completeness, or canonical content hashes.
