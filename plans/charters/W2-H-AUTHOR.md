# Charter W2 H-AUTHOR — persistent author coordinator role

Spec: §14 (rebuttal workflow), §26 (truthfulness gate), §28.H,
PHASED_ROLE_ARCHITECTURE R2.4 (persistent author coordinator with rebuttal
and final-followup phases; response workers are transient drafting helpers,
never separate authors, never direct publishers). Depends on: W0, W1-D
runner. Develops against CF's fixture reviews before live integration.
Reviewer followup/discussion phases belong to CF-REVIEWERS, not this lane.

## Owns
`roles/author/` (PRD.md, ROLE_SPEC.md, PROMPT.base.md, schemas/,
workers/response-draft-worker/{SPEC.md,PROMPT.md},
phases/{rebuttal,final-followup}/{SPEC.md,PROMPT.md,tasks.template.json}),
`tests/fixtures/author/`.

## Deliverables
1. `roles/author/` role documents: one persistent Author Coordinator
   identity owning evidence boundary, response matrix, cross-review
   consistency, commitments, admitted limitations, and ALL published
   responses (R2.4).
2. Response-draft workers (workers/response-draft-worker/): transient
   helpers drafting per-review responses in PARALLEL inside the author
   workspace; they cannot publish — only the coordinator publishes
   (checker-enforced).
3. Evidence boundary (§14.3) enforced by checker: allowed sources only;
   truthfulness gate (§26) rejects invented experiments/results/citations/
   proofs. Response matrix per §14.4 with response labels
   (already_in_paper … cannot_answer_without_new_research).
4. Phase `rebuttal` (gate: initial-review freeze, R2.10): subscription
   wake-up on each published official review, rebuts whichever arrives
   first — parallel drafting across threads, one rebuttal per official
   review, cross-review consistency gate before publishing.
5. Phase `final-followup` (gate: reviewer follow-ups published): answers
   ONLY newly raised follow-up questions, one final response per applicable
   reviewer; prior commitments carried in role state, contradictions with
   earlier responses rejected.

## Done when
- Truthfulness gate tests: invented-experiment claim rejected, invented
  citation rejected, contradiction between two thread responses caught by
  consistency gate.
- Fake-agent tests: polling wake-up order (reviews arriving at different
  times), thread settlement, worker-cannot-publish enforcement, identity
  continuity from rebuttal to final-followup (same coordinator id, response
  matrix and commitments persisted).
- REAL run: rebuttal produced against CF's 34584 fixture review; every
  weakness addressed or honestly unresolved.
- Committed fixture: full thread (review → rebuttal → follow-up → final)
  for viewer/K2 integration.
- STATUS.md written.
