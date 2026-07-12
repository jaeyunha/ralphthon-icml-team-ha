# Validator artifact schema proposals

## Scope

This directory is an integration-ready, additive schema proposal. It does not modify frozen `packages/contracts` or `packages/schemas`.

It covers every retained custom G2 mathematical runtime artifact:

- mathematical claim inventory;
- assumption, symbolic identity/gradient, SMT, shape, equation-to-code, and numerical tool evidence;
- Lean formal-proof result with distinct proof-validity and formalization-fidelity fields;
- independent-confirmation report;
- persistent finding ledger;
- mathematical validation bundle.

It also replaces the permissive role-local G3 arbitration wrapper with a strict shared-schema candidate for the finalized frozen validation bundle. Atomic findings remain governed by the existing shared `validation-finding.schema.json`.

## Strictness decisions

- Every object uses `additionalProperties: false`.
- Status, role-lane, phase-order, tool-version, digest, and resolution vocabularies are bounded.
- Mathematical tool evidence is a strict `oneOf` union whose branches are distinguishable by required fields.
- Accepted Lean proofs require an attempted, compiled proof and compiler exit code zero.
- Statement mismatch forces `formalization_fidelity: mismatch`; proof acceptance cannot override it.
- Numerical evidence records the complete required exact/high-precision/interval/property/exhaustive/boundary method sequence.
- The G3 bundle embeds only shared-schema-valid findings and preserves conflicts as `surfaced_not_averaged`.
- The validator script additionally checks relationships that JSON Schema cannot express portably: finding counts, ledger/bundle agreement, confirmation counts, G3 conflict references, source-lane coverage, and canonical content hashes.

## Promotion mapping

`inference-map.json` gives:

1. exact path inference for every committed G2 retained artifact and the finalized G3 bundle;
2. proposed canonical filename prefixes for new artifacts;
3. legacy aliases needed to validate the already committed fixtures without renaming them.

INTEGRATE can copy the seven schemas into `packages/schemas/schemas/`, add the canonical aliases to `scripts/validate-run.sh`, regenerate types, and add the examples to shared valid/invalid contract fixtures.

## Verification

Run from repository root:

```sh
uv run python plans/schema-change-requests/004-validator-artifact-schema-proposals/validate_proposals.py
```

The command checks schema validity, valid/invalid examples, complete path coverage, all committed target fixtures, and semantic invariants.
