# W3-I Shared Contract Request — Benchmark terminal arm decisions

Owner request: Lane C (persistent AC/SAC/PC roles)  
Shared implementation owner: INTEGRATE only

## Need

Stage A role-local runtimes now require additive shared contracts for an arm-scoped W3 path without changing historical single-paper/batch decision semantics.

## Requested additive schemas

1. `terminal-arm-input` version 1
   - `campaign_id`, `arm_cohort_id`.
   - `slots`: exactly seven, ordered and uniquely keyed by `paper_slot` 1 through 7 and unique `paper_id`.
   - Each slot is exactly one of:
     - validated AC meta-review: `status: meta_review`, frozen `meta-review` artifact or reference, artifact SHA-256, and passed validation record (`schema_id`, `validator_id`, timestamp);
     - typed paper-row failure: `status: paper_failure`, terminal failure code/stage/message/timestamp/evidence refs.
   - Cross-arm readers must reject the input.

2. `benchmark-sac-calibration-bundle` version 1
   - Same campaign/arm keys and exactly seven ordered slots.
   - Valid rows carry AC recommendation, recommended binary decision, meta-review ref/hash, SAC rationale/evidence, and action history.
   - Allowed action vocabulary: `affirm`, `request_meta_review_revision`, `procedural_fail`.
   - Revision history permits at most one defect-scoped AC meta-review revision followed by one SAC reconsideration.
   - Existing paper failures remain failed while other valid rows continue.
   - `adaptive_review_required`, SAC procedural failure, or SAC phase failure project all seven slots failed; no emergency/fifth reviewer.

3. `benchmark-pc-decision` version 1
   - Campaign/arm/paper-slot/paper IDs and PC identity.
   - `outcome` exactly `accept | reject | failed`.
   - Reason, evidence refs, AC meta-review ref, SAC bundle ref, unresolved dissent, terminal failure code, immutable decision hash, timestamp.
   - `failed` requires a terminal failure code and null meta-review ref; valid binary outcomes require meta-review provenance and no terminal failure code.
   - No Spotlight field or Spotlight outcome.

4. `benchmark-arm-decision-bundle` version 1
   - Exactly seven unique ordered `benchmark-pc-decision` entries.
   - PC identity, SAC bundle hash, action-history/ref linkage, runtime evidence roots and reconciliation roots supplied by their owning lanes, bundle hash, timestamp.
   - Publication gate: all seven immutable PC slot artifacts exist before the arm bundle.

5. `benchmark-arm-freeze` version 1
   - Binds a validated arm decision bundle plus all seven paper ledgers and required reconciliation/provenance roots.
   - Arm failure freezes remain valid terminal artifacts with seven failed rows.

## Requested phase gates

Add W3 facts without changing existing historical facts:

- AC reviewer coverage: requires proposed fixed panel; produces validated four-reviewer coverage.
- AC review quality: requires four official reviews; produces complete quality assessment.
- AC discussion: requires author/reviewer rounds complete; produces terminal issue ledger and final-justification completeness.
- AC meta-review: requires all decisive issues resolved or irreducibly disputed; produces validated immutable AC meta-review.
- SAC calibration: requires exact seven terminal arm slots; produces validated calibration bundle or typed arm failure.
- PC finalization: requires valid SAC bundle; produces seven immutable PC artifacts, then arm bundle.
- Arm freeze: requires valid arm bundle and paper ledgers.

## Dual-reader requirement

Keep `decision.schema.json` version 1 byte-compatible. Add readers that project benchmark `accept`, `reject`, and `failed` into viewer/public presentation without inventing `spotlight_candidate`, `accept_regular`, or `accept_spotlight`.

## Role-local reference implementation

- `roles/sac/arm_input.py`
- `roles/sac/runtime.py`
- `roles/pc/runtime.py`
- `roles/{ac,sac,pc}/schemas/`
- `tests/test_w3_roles.py`
