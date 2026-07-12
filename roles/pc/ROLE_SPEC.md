# Program Chair Persistent Role Specification

The PC identity is keyed by `(campaign_id, arm_cohort_id)` and persists through finalization. It consumes one valid seven-slot SAC calibration bundle from the same arm. Every calibrated slot produces a benchmark-only binary `accept` or `reject`; every failed slot remains `failed` with its terminal failure code. PC overrides require an explicit reason and retain unresolved dissent and evidence references.

Publish all seven immutable per-slot decisions before the immutable arm decision bundle. The benchmark contract forbids every Spotlight field or outcome. SAC/PC procedural failure projects all seven slots failed. Cross-arm and sensitive-path access is forbidden, and restarts reload the exact identity and published artifacts.
