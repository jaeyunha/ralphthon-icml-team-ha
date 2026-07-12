# Schema change request — reviewer calibration profile V2

## Requester

Lane B — immutable reviewer calibration profiles

## Shared schema gap

The frozen official-review contract has no field for the required direct overall judgment. Calibration V2 must state the strongest evidence-backed acceptance case, strongest evidence-backed rejection case, which one dominates, why it dominates, and the evidence-anchored significance basis. Encoding this in `summary`, `limitations`, or score fields would violate their existing semantics.

The frozen follow-up contract also leaves `concern_resolutions` untyped and models `new_questions` as bare strings. Calibration V2 requires every partial or unresolved concern to select exactly one answer-induced, decision-relevant question or a structured `no_new_question_reason`; an empty question list without per-concern reasons must fail.

## Requested INTEGRATE-owned additive change

1. Add a profile-V2 official-review schema or additive version that requires:
   - `overall_judgment.acceptance_case` with text and stable anchors;
   - `overall_judgment.rejection_case` with text and stable anchors;
   - `overall_judgment.dominant_case` as `acceptance|rejection`;
   - `overall_judgment.dominance_rationale`;
   - `overall_judgment.significance_basis` with text and stable anchors.
2. Add a profile-V2 follow-up schema or additive version that:
   - types concern status as `resolved|partially_resolved|unresolved|invalidated_by_response`;
   - requires every partial/unresolved concern to contain exactly one of `new_question_id` or `no_new_question_reason`;
   - types new questions with `id`, `concern_id`, `question`, non-empty `answer_induced_by`, and `decision_relevance`;
   - preserves version-1 readers unchanged.
3. Generate TypeScript types and dual readers for the additive profile-V2 artifacts.
4. Add valid/invalid fixtures mirroring the lane-local schemas under `roles/reviewer/profiles/v2/`.

## Lane-local evidence

Lane B implements role-local V2 schemas, checker gates, immutable profile hashing, and synthetic behavior fixtures without modifying `packages/contracts/**`, `packages/schemas/**`, generated code, or production scripts. INTEGRATE remains the sole shared owner.
