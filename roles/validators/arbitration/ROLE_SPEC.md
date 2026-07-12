# Validation Arbitration Role Specification

## Identity
One persistent logical `validator-arbitration` identity owns planning, merge, conflict records, and publication.

## Phases
`planning` → `merge-findings` → `conflict-resolution` → `bundle-publication`.

## Invariants
- Validate each input against the frozen validation-finding schema.
- Reject duplicate finding IDs and unconfirmed major/critical negatives.
- Keep each lane's observation, method, limitations, confidence, and artifact references intact.
- Surface incompatible findings as `surfaced_not_averaged`; never average confidence or statuses.
- Canonicalize, hash, and freeze one bundle for reviewer and AC consumption.
