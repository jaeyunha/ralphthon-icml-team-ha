# Senior Area Chair Persistent Role Specification

The SAC identity is keyed by `(campaign_id, arm_cohort_id)` and persists for the arm calibration phase. It consumes exactly seven ordered terminal slots. Each slot is either a schema-validated AC meta-review with a matching content hash or a typed paper-row failure. Existing failed rows remain failed while valid rows continue.

Allowed actions are `affirm`, one bounded `request_meta_review_revision` followed by one reconsideration, or `procedural_fail`. An emergency-review need becomes the typed arm failure `adaptive_review_required`; no fifth reviewer is created. SAC/procedural/adaptive failures project all seven arm slots to terminal failures. Cross-arm and sensitive-path access is forbidden. The published calibration bundle and action history are immutable and retain every revision action.
