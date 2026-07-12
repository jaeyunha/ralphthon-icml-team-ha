# Charter W3 I-DECISION — persistent AC/SAC/PC roles

Spec: §16 (issue-based discussion), §17 (AC/SAC/PC), §18 (decision
semantics), §28.I, PHASED_ROLE_ARCHITECTURE R2.5–R2.6. AC is ONE persistent
identity across four phases (reviewer-coverage → review-quality-check →
discussion-moderation → meta-review); SAC has calibration, PC has
finalization. Depends on: W2 CF + H fixtures (full threads), G arbitration
bundle fixture.

## Owns
`roles/ac/`, `roles/sac/`, `roles/pc/` (each: PRD.md, ROLE_SPEC.md,
PROMPT.base.md, schemas/, phases/*/{SPEC.md,PROMPT.md,tasks.template.json}),
`tests/fixtures/decision/`.

## Deliverables
1. `roles/ac/` with persistent state per R2.5 (panel + coverage assessment,
   review-quality judgments, issue ledger, discussion summaries, expertise
   weighting, final recommendation persist across all four phases).
2. AC phase `reviewer-coverage` (gate: personas proposed): §10.4 panel gate
   as the AC's own judgment loop — coverage report artifact.
3. AC phase `review-quality-check` (gate: official reviews published):
   quality flags feeding discussion triggers.
4. AC phase `discussion-moderation` (§16): issue-based threads only (no
   group chat); trigger detection (score spread, contradictory factual
   conclusions, theorem/novelty disagreement, low-quality review...);
   round protocol (open targeted issue → named reviewers answer
   independently → summarize → close or one narrower follow-up);
   termination predicates incl. `irreducibly_disputed` for score
   oscillation; consensus NOT required.
5. AC phase `meta-review` (§17.1): ten sections, evidence-grounded, weighs
   expertise/confidence, preserves dissent, engages the strongest opposing
   argument, NEVER score-averages (checker-enforced: decision rationale
   must cite issues/evidence, and an averaging shortcut is a reject).
6. `roles/sac/` phase `calibration` (§17.2): action vocabulary (confirmed …
   recommend_decision_change), borderline consistency, emergency-review
   trigger.
7. `roles/pc/` phase `finalization` (§17.3): procedural completion
   validation, escalation resolution, final decision + §18 semantics
   (single-paper: accept/reject + spotlight_candidate flag), decision
   artifact with unresolved dissent recorded.
   (Reviewer discussion-participation lives in roles/reviewer/phases/
   discussion — CF-REVIEWERS lane.)

## Done when
- Fake-agent tests: trigger detection matrix, oscillation →
  irreducibly_disputed, averaging-shortcut rejection, dissent preservation
  in decision artifact, AC identity + issue ledger continuity from coverage
  through meta-review (R2.5).
- REAL run: full chain (discussion → meta-review → SAC → PC) over the 34584
  fixture threads produces a schema-valid decision with evidence refs.
- STATUS.md written.
