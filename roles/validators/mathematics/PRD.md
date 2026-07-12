# Mathematical Validation Coordinator PRD

## Purpose

Produce tool-grounded, anchor-resolving evidence about mathematical claims without assigning ICML scores or recommendations. One persistent coordinator owns the claim inventory, phase history, proof artifacts, and final finding ledger.

## Required capabilities

- Extract definitions, equations, lemmas, theorems, assumptions, dependencies, complexity and convergence claims, and statistical derivations from the verified dossier.
- Audit undefined symbols, quantifiers, hidden assumptions, circular dependencies, scope mismatch, boundary cases, and unsupported generalization.
- Run SymPy algebra, calculus, matrix, recurrence, and probability checks; Z3 implication and counterexample checks; exact/high-precision numerical searches; shape checks; and equation-to-code comparisons.
- Run Lean 4 in the repository-pinned, network-disabled container. Report proof validity separately from formalization fidelity.
- Require an independent confirmation path before a high-impact negative finding may be published as major or critical.
- Publish only frozen-schema validation findings with resolving dossier anchors.

## Non-goals

The coordinator does not review novelty, score the submission, recommend acceptance, browse literature, execute untrusted research code outside the code-validation sandbox, or treat a compiling Lean theorem as automatic verification of the paper theorem.

## Success criteria

Every phase uses the same logical agent identity and a hashed input manifest. The planted symbolic error, hidden assumption, correct lemma, and mismatched Lean statement are classified correctly. The real paper 34584 dossier produces schema-valid findings with retained tool evidence.
