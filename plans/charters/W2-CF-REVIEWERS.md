# Charter W2 CF-REVIEWERS — persona compiler + reviewer role (all phases)

Spec: §10 (persona system), §13 (reviewer loops), §15 (follow-up),
sections 4.1–4.3 and 28.C+F, PHASED_ROLE_ARCHITECTURE R2.1–R2.3 +
R2.8–R2.12. The reviewer is ONE persistent logical role with four phase
modules — initial-review, followup, discussion, final-justification.
Depends on: W0 contracts, W1-D runner, W1-B extraction fixture, W1-E broker
contract (develop against its request/response file fixtures).

## Owns
`engine/loops/persona-compiler/`, `roles/reviewer/` (PRD.md, ROLE_SPEC.md,
PROMPT.base.md, schemas/, phases/{initial-review,followup,discussion,
final-justification}/{SPEC.md,PROMPT.md,tasks.template.json}),
`tests/fixtures/reviewers/`.

## Deliverables
1. Persona compiler loop: dossier → domain classification → 4 personas
   (§10.2 schema; add 5th/6th only per §10.1 triggers), deep-audit coverage
   assignment (§10.3), persona gate checker (§10.4: no duplicates, coverage,
   no encoded verdicts/harshness — regex + judge check). Personas are
   frozen into each reviewer's runtime identity (R2.8).
2. `roles/reviewer/` role documents: PRD.md (design-time only, never in
   prompts), ROLE_SPEC.md invariants (identity/persona continuity, ledger
   formats, immutable official-review version, allowed score-update
   semantics), PROMPT.base.md (stable behavior: whole paper, evidence-first,
   §13.5 score semantics, calibration priors from
   `openreview_icml2026_spotlight_analysis/analysis/calibration_stats.md`).
3. Phase `initial-review`: SPEC.md (R2.1 visibility: no other reviews/
   personas/rebuttals/AC/benchmark), PROMPT.md, tasks.template.json with
   the §13.3 task queue (comprehension → contribution-map → claim-audit →
   theory-audit → experiment-audit → related-work-plan →
   literature-research → validation-bundle-review → severity-calibration →
   score-calibration → assembly → self-audit), one task per invocation.
   Produces immutable official-review v1 + concern ledger.
4. Phase `followup`: SPEC.md (adds own review, own ledger, own-thread
   rebuttal, validation updates; still NOT other reviews), per-concern
   resolution per §15 (resolved/partially_resolved/unresolved/
   invalidated_by_response), score changes APPEND to score-history with
   mandatory reasons, no moving goalposts.
5. Phase `discussion`: SPEC.md (R2.1 discussion visibility: all published
   reviews/responses, AC issues, positions), issue-specific position
   artifacts; possible score update with reason.
6. Phase `final-justification`: full permitted record; freezes immutable
   final-review + final score rationale.
7. Review checker per phase: §13.4 gate executable (anchors resolve, scores
   match prose, no averaging, confidence vs verification depth, summary not
   copied from abstract, schema-valid); ledger-consistency checks (every
   weakness has a concern-ledger entry).

## Done when
- Persona gate tests: duplicate panel rejected, verdict leakage rejected,
  coverage gap triggers 5th reviewer.
- Fake-agent tests: task-queue discipline, checker reopens, identity
  continuity across all four phases (same agent id, persona, ledgers),
  followup cannot read another reviewer's review (manifest test),
  score-history append-only.
- REAL run: 4 personas compiled for the 34584 fixture; at least one full
  reviewer initial-review phase produces a schema-valid official review
  with resolving anchors on the real paper.
- Committed fixtures: personas + one official review + one followup
  artifact for 34584.
- STATUS.md written.
