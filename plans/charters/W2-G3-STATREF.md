# Charter W2 G3-STATREF — statistical, reference, ethics validators + arbitration

Spec: §12.4 (statistics), §12.6 (references), §12.7 (ethics), §12.1
(arbitration → frozen validation bundle), §28.G, PHASED_ROLE_ARCHITECTURE
R2.7 (each validator = one persistent role with phase modules:
roles/validators/{statistics,references,ethics,arbitration}/). Depends on:
W0, W1-D, W1-B fixture, W1-E broker (reference lookups go through the
broker).

## Owns
`roles/validators/{statistics,references,ethics,arbitration}/`,
`engine/validators/{statistics,references,ethics,arbitration}/` (helpers),
`tests/fixtures/validators-statref/`.

## Deliverables
1. Statistical validator loop (§12.4): seeds/runs/error bars/CI/significance/
   effect sizes/multiple comparisons/leakage/split integrity/baseline
   fairness/metric correctness; claim-breadth vs evidence-breadth
   comparison; robustness axes recorded.
2. Reference validation workers (§12.6): extractor + identity validator
   (statuses verified_exact … confirmed_nonexistent), citation-support
   validator (directly_supports … source_never_makes_claim), related-work
   coverage researcher (via broker), retraction/version validator,
   attribution/priority, integrity auditor. Rebuttal-challenge path:
   recheck evidence, don't defend first result (§12.6).
3. Ethics/integrity validator (§12.7): trigger conditions, evidence +
   recommended flag only, never declares misconduct.
4. Validation arbitration (§12.1): merge all validator outputs into ONE
   frozen validation bundle consumed by reviewers and AC; conflicting
   findings surfaced, not averaged away.
5. Validation planner: dossier → which validators run with which claim
   targets (§12.1 diagram entry point).

## Done when
- Planted-defect suite: fake reference caught, misquoted citation caught
  (source_never_makes_claim), leakage fixture caught, unfair baseline
  caught.
- Arbitration produces schema-valid frozen bundle from all three lanes'
  fixture findings (coordinate with G1/G2 fixture formats via INTEGRATE).
- REAL run: reference validation on 34584's bibliography through the
  broker.
- STATUS.md written.
