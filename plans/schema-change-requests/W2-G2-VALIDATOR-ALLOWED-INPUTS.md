# Schema change request — typed mathematical validator evidence

## Requester

W2-G2-MATHVAL

## Resolved dependency

INTEGRATE approved the bounded `validator_mathematics` role for `allowed-inputs.json` in commit `8ce2eec` (schema request 002). G2's canonical hashed phase manifests validate against that approved schema once this lane is integrated onto current main. No additional permission vocabulary is required.

## Remaining frozen-schema gap

The mathematical lane retains protocol artifacts whose semantics must not be collapsed into the shared `validation-finding` schema:

- mathematical claim inventory;
- SymPy, Z3, exact/high-precision/interval numerical, shape, and equation-to-code evidence;
- Lean proof results with separate `proof_validity` and `formalization_fidelity`;
- independent-confirmation report;
- persistent finding ledger;
- published mathematical validation bundle.

Every individual published finding already validates against `validation-finding.schema.json`. Shared `identity`, `role-state`, and `phase-state` documents also validate against their frozen schemas. `scripts/validate-run.sh` cannot validate the full retained evidence directory until the artifact types above receive approved schemas or an explicit typed validator-evidence union.

## Requested integration-owned change

1. Add shared schemas (or one explicit typed validator-evidence union) for the retained mathematical artifacts above.
2. Preserve the requirement that proof validity and formalization fidelity are separate fields and that `Lean proof accepted` does not imply paper-theorem verification.
3. Extend `validate-run.sh` inference/control-manifest fixtures for the approved artifact names.
4. Regenerate TypeScript types and add valid/invalid fixtures before marking the request applied.

## Lane behavior pending arbitration

G2 keeps full machine-readable tool and proof evidence rather than dropping fields or inventing a generic fallback. The lane does not edit frozen contracts or schemas. Its tests directly validate the approved validator manifests, shared runtime-state documents, and every published finding; only full-directory validation of the typed protocol artifacts remains integration-owned.
