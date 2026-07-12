# Charter W2 G2-MATHVAL — mathematical validation workers

Spec: §12.3, §28.G, PHASED_ROLE_ARCHITECTURE R2.7: ONE persistent
`roles/validators/mathematics/` role with phases claim-extraction →
assumption-audit → symbolic-validation → counterexample-search →
formalization → confirmation → bundle-publication. Depends on: W0, W1-D
runner, W1-B fixture (dossier theorem/equation inventory). FULL
implementation including Lean.

## Owns
`roles/validators/mathematics/` (role + phase modules),
`engine/validators/math/` (Python helpers), `tests/fixtures/validators-math/`.

## Deliverables
1. Worker topology per §12.3 mapped onto R2.7 phases of one persistent
   coordinator identity:
   claim extractor, assumption/dependency auditor, symbolic validator
   (sympy: algebraic equivalence, gradients, matrix identities,
   derivatives/integrals, probability expressions), logic/SMT validator
   (z3), numerical counterexample search (exact/high-precision/interval
   arithmetic, property tests, boundary + adversarial search), shape/
   dimension validator, equation-to-code validator (works with G1
   implementations when available).
2. Formal proof validator: Lean 4 toolchain in a pinned container;
   the §12.3 five-step protocol — formalize, SEPARATELY audit statement
   alignment, attempt proof, compile, report proof validity and
   formalization fidelity as distinct fields. `Lean proof accepted ≠ paper
   theorem verified` encoded in the finding schema usage.
3. Status vocabulary exactly §12.3 (verified_formally …
   tool_unsupported). High-impact negative findings require a second
   confirmation path before severity `major` (§12.3, §26).
4. Findings anchored to theorem/equation anchors from the dossier.

## Done when
- Planted-defect suite: fixture paper snippets with (a) an algebraic
  identity error caught symbolically, (b) a theorem with a hidden
  assumption caught by counterexample search, (c) a correct lemma
  verified, (d) a statement-mismatch Lean formalization reported as
  mismatch not success.
- Second-confirmation-path rule enforced in tests.
- REAL run: math validation coordinator over the 34584 fixture dossier
  produces schema-valid findings.
- STATUS.md written.
