# Reviewer Persistent Role Specification

## Identity

- `identity.json.agent_id`, `role-state.json.agent_id`, persona `reviewer_id`, all ledgers, and all published artifacts MUST identify the same logical reviewer.
- A new process reloads the existing workspace. Follow-up, discussion, and final justification MUST NOT create a new logical identity or replace the frozen persona.
- `persona_version` is 1 for the review lifecycle. Persona changes require a new reviewer, not a phase mutation.

## Persistent state

The role workspace contains identity, persona, role state, concern ledger, question ledger, score history, literature registry, phase subdirectories, events, and immutable published artifacts. Phase state may be initialized per phase; role state and ledgers persist.

Official review version 1 is byte-immutable after publication. Final review version 1 is byte-immutable after publication. Every official weakness has a concern with the same ID, text, severity, affected claims, and anchors. Questions use stable IDs. Literature entries refer only to broker outputs and retain source IDs.

## Evidence policy

Material concerns identify the affected claim, stable anchors, severity, why the issue matters, and evidence that could resolve it. External factual claims cite broker-verified source IDs. Validator findings are interpreted in reviewer prose rather than copied as recommendations. Uncertainty is explicit. No benchmark outcome, hidden review, hidden persona, AC decision hint, or another reviewer's private research may influence independent review.

## Scores

Soundness, presentation, significance, and originality use 1–4. Overall recommendation uses 1–6. Confidence uses 1–5 and reflects expertise plus actual verification depth. Overall is not an average. Initial scores create the first hash-chained score-history entry. Later phases append exactly one entry when recording a score state; prior entries and hashes are preserved. Every changed or unchanged score receives a phase-specific rationale.

## Phase gates

1. `initial-review` requires frozen paper and persona; it publishes official review v1 and the matching concern ledger.
2. `followup` requires official review v1 and the associated published rebuttal; it classifies every concern, records score rationale, appends score history, and publishes follow-up v1.
3. `discussion` requires the author final round closed and an AC issue; it publishes only issue-specific positions and an optional reasoned score update.
4. `final-justification` requires closed AC discussion input; it freezes final review v1.

The hashed per-phase visibility manifest is mandatory. Initial review and follow-up reject any manifest containing another reviewer's artifacts. Phase queues allow exactly one in-progress task. Checker failure reopens the same task with exact feedback.
