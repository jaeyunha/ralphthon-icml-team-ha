# Schema change request 002 — validator allowed-input manifests

## Requesters

W2-G2-MATHVAL and W2-G3-STATREF.

## Frozen schema

`packages/schemas/schemas/allowed-inputs.schema.json`

## Problem

The phased-role architecture requires a hashed `allowed-inputs.json` for every
validator phase. The frozen schema only admitted reviewer, author, AC, SAC, and
PC identities, so canonical persistent validator identities could not validate.

## INTEGRATE decision

Approved as a strictly additive role-enum extension. Add the six bounded W2
validator identities:

- `validator_code`
- `validator_mathematics`
- `validator_statistics`
- `validator_references`
- `validator_ethics`
- `validator_arbitration`

The existing permission and input-category vocabularies already express the W2
visibility requirements, so no broader permission value is added. In
particular, this change does not weaken reviewer isolation or path confinement.

Generated TypeScript types and schema tests must be updated. A generic
unbounded `validator` role remains invalid.
