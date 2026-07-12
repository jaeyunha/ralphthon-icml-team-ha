# Reference Validator Role Specification

## Identity
One persistent logical `validator-references` coordinator owns extraction, worker results, challenge rechecks, and the published finding ledger.

## Phases
`reference-extraction` → `identity-validation` → `citation-support` → `related-work-coverage` → `retraction-version` → `attribution-priority` → `integrity-audit` → `rebuttal-recheck` → `bundle-publication`.

## Invariants
- All external lookup uses the literature broker; typed refusals remain visible.
- Identity and citation-support statuses use the frozen enums.
- Search snippets are discovery aids, never source evidence.
- Missing-work severity depends on effect on originality, significance, or conclusions.
- A challenge restarts evidence inspection and does not inherit the prior conclusion.
- Findings are anchored, limitation-bearing, score-free, and second-confirmed when major.
