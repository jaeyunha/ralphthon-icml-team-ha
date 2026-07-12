# Schema change request 003 — frozen validation bundle

## Request

Promote the role-local `roles/validators/arbitration/schemas/validation-bundle.schema.json` into the frozen shared schema set after integration review.

## Reason

Charter W2-G3 requires one schema-valid frozen arbitration bundle consumed by reviewers and AC, while W0 defines only individual `validation-finding` objects. The role-local schema preserves every frozen finding, source lanes, explicitly surfaced conflicts, a freeze timestamp, and a canonical SHA-256 content hash.

Validator input manifest roles were separately approved on integrated main in commit `8ce2eec`; Lane G3 emits the approved `validator_statistics`, `validator_references`, `validator_ethics`, and `validator_arbitration` role values and matching permission structure.

## Compatibility

This is additive. Existing validation findings remain the atomic evidence contract. Arbitration validates every item against the frozen finding schema before validating and hashing the wrapper. No reviewer or decision schema changes are required.
