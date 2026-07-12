# STATUS W2-G2-MATHVAL

## State

Implementation complete in the G2-owned paths. The lane uses one persistent `validator` identity with role instance `mathematics` across the required phase order:

`claim-extraction → assumption-audit → symbolic-validation → counterexample-search → formalization → confirmation → bundle-publication`.

## Delivered

- Persistent role modules under `roles/validators/mathematics/`: PRD, role specification, base prompt, and SPEC/PROMPT/task templates for all seven phases.
- Python validation package under `engine/validators/math/` with pinned dependencies:
  - SymPy algebraic equivalence and gradient checking;
  - Z3 satisfiability, implication, invariant, and finite-domain counterexample checks;
  - exact rational, 80-digit, interval-enclosure, deterministic property, exhaustive-small-case, boundary, and adversarial numerical search;
  - tensor shape propagation;
  - equation-to-code comparison with an explicit G1 conformance-artifact adapter contract;
  - a persistent coordinator that emits hashed phase input manifests, shared-schema-valid identity/role/phase state, retained tool artifacts, a finding ledger, and immutable published findings.
- Full Lean five-step protocol in a network-disabled, read-only, capability-dropped, resource-limited container pinned to:
  - image digest `leanprovercommunity/lean4@sha256:d61f7052fa82e7e726db46984ef4f11c84525eabd4a8d1d20ba80f1ccee34018`;
  - Lean `4.10.0`.
- Formal proof artifacts report `proof_validity` and `formalization_fidelity` separately and encode the invariant that a compiling Lean theorem does not by itself verify the paper theorem.
- Second-confirmation enforcement rejects missing, self-referential, unavailable, and same-method confirmation paths for high-impact negative findings.
- Planted fixtures under `tests/fixtures/validators-math/planted/` covering:
  - symbolic algebra error;
  - hidden nonnegative-domain assumption with concrete counterexample;
  - correct symbolic and Lean lemmas;
  - a compiling but statement-mismatched Lean formalization;
  - shape validation;
  - equation-to-code mismatch and G1 adapter input.
- Real paper 34584 run under `tests/fixtures/validators-math/34584/run/`:
  - 22 dossier theorems and 178 equations retained in the claim inventory;
  - five schema-valid anchored findings;
  - representative Reynolds-operator symbolic and numerical checks;
  - exact Z3 two-site transporter specialization;
  - block-kernel shape check;
  - Full OENN UAT assumption/scope audit;
  - no ICML scores or acceptance recommendation.

## Verification evidence

- `cd engine/validators/math && uv run pytest tests -q` — **6 passed**. This executes the real pinned Lean container for both the correct lemma and statement-mismatch case, the planted defects, the independent-confirmation rejection path, shared identity/role/phase schema checks, committed-fixture validation, and the real 34584 coordinator.
- `cd engine/validators/math && uv run ruff check math_validator tests` — **passed**.
- `uv run pytest engine/extraction tests/test_contract_schemas.py tests/test_validate_run.py -q` — **113 passed**.
- `uv run pytest -q` — **93 passed**.
- `bun install --frozen-lockfile && bun test` — **130 passed, 8 skipped, 0 failed**.
- Approved-schema check against main `8ce2eec` — **14 validator phase manifests valid**.
- Real coordinator CLI — **completed, 5 findings** for submission `34584`.
- Every committed published finding is validated directly against `validation-finding.schema.json`, and every cited paper anchor resolves through the real 34584 `anchors.json`.
- Lean mismatch evidence records `proof_validity: accepted` and `formalization_fidelity: mismatch`, causing the published status `statement_mismatch` rather than success.

## Integration arbitration

INTEGRATE approved `validator_mathematics` for `allowed-inputs.json` in main commit `8ce2eec` (schema request 002); the committed phase manifests validate against that approved schema when this lane is integrated. No frozen contract or schema was edited in G2. `plans/schema-change-requests/W2-G2-VALIDATOR-ALLOWED-INPUTS.md` now requests only typed schemas for the retained claim/tool/Lean/confirmation/ledger/bundle evidence. Full-directory `scripts/validate-run.sh` remains blocked on those artifact schemas, while shared `identity`, `role-state`, `phase-state`, allowed-input manifests, and every individual validation finding are already schema-valid.
