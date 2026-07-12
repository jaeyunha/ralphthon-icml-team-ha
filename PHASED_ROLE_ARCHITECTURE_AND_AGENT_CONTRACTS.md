# Phased Role Architecture and Agent Contracts

---

# Revision 2 — Persistent Roles with Phase-Specific Ralph Loops

> **This section is authoritative where it differs from earlier role naming or directory examples.**

The system must distinguish between:

1. a **persistent logical agent identity**;
2. the **phase-specific loop** currently being executed;
3. the individual short-lived model invocation used by Ralph.

The correct abstraction is:

```text
One logical role identity
    ↓
One role-level PRD
    ↓
One role-level invariant specification
    ↓
One base role prompt
    ↓
Several phase-specific SPEC.md files
    ↓
Several phase-specific PROMPT.md files
    ↓
Many resumable Ralph invocations inside each phase
```

A new LLM process may be launched for every Ralph iteration, but it remains the same logical agent when it reloads the same identity, persona, state, history, and workspace.

## R2.1 Why phase separation is required

The reviewer’s responsibilities, permissions, inputs, outputs, and completion conditions change substantially across the review lifecycle.

### Initial review

The reviewer may read:

- frozen submission;
- assigned persona;
- common venue rubric;
- admissible literature evidence;
- frozen validator evidence made available for official-review finalization.

The reviewer must not read:

- other reviewer personas;
- other reviews;
- author rebuttals;
- AC opinions;
- benchmark decisions.

### Reviewer follow-up

The same reviewer identity may additionally read:

- its own official review;
- its own concern ledger;
- the author rebuttal associated with its review;
- score history;
- validation updates explicitly published for the response phase.

### Internal discussion

The same reviewer identity may additionally read:

- all published official reviews;
- all published author responses;
- AC-created discussion issues;
- other reviewers’ issue-specific positions;
- shared validation evidence.

### Final justification

The reviewer reads the complete permitted process record and publishes its final review state and final score rationale.

These visibility transitions must be enforced by the phase SPEC and `allowed-inputs.json`, not merely described in prose.

## R2.2 Persistent reviewer role

Reviewer R2 is one logical agent:

```text
Reviewer R2
├── Initial Review Ralph Loop
├── Reviewer Follow-Up Ralph Loop
├── Internal Discussion Ralph Loop
└── Final Justification Ralph Loop
```

The following data persists across all phases:

- reviewer ID;
- persona and expertise;
- known blind spots;
- literature registry;
- original official review;
- concern ledger;
- question ledger;
- score history;
- evidence references;
- discussion positions;
- commitments and acknowledged uncertainty.

The reviewer does not become a new reviewer when follow-up or discussion begins.

## R2.3 Reviewer design-time directory

```text
roles/reviewer/
├── PRD.md
├── ROLE_SPEC.md
├── PROMPT.base.md
├── schemas/
│   ├── concern-ledger.schema.json
│   ├── score-history.schema.json
│   ├── official-review.schema.json
│   ├── followup.schema.json
│   ├── discussion-position.schema.json
│   └── final-review.schema.json
└── phases/
    ├── initial-review/
    │   ├── SPEC.md
    │   ├── PROMPT.md
    │   └── tasks.template.json
    ├── followup/
    │   ├── SPEC.md
    │   ├── PROMPT.md
    │   └── tasks.template.json
    ├── discussion/
    │   ├── SPEC.md
    │   ├── PROMPT.md
    │   └── tasks.template.json
    └── final-justification/
        ├── SPEC.md
        ├── PROMPT.md
        └── tasks.template.json
```

### Reviewer `PRD.md`

Defines the permanent product responsibility:

- independently evaluate the whole paper;
- contribute a complete ICML-style review;
- preserve neutrality and uncertainty;
- research literature through the broker;
- interpret validator evidence;
- respond to rebuttal;
- participate in AC discussion;
- publish a final justified recommendation.

### Reviewer `ROLE_SPEC.md`

Defines permanent invariants:

- identity continuity;
- persona continuity;
- evidence and citation policy;
- score ranges;
- concern-ledger format;
- score-history format;
- phase-transition rules;
- independence requirements;
- immutable original-review version;
- allowed score-update semantics.

### Reviewer `PROMPT.base.md`

Contains stable model-facing behavior:

- evaluate the whole paper;
- remain neutral and evidence-first;
- do not invent evidence;
- state uncertainty;
- use stable anchors;
- preserve identity and previous commitments;
- do not seek consensus for its own sake.

### Phase `SPEC.md`

Defines:

- visible inputs;
- prohibited inputs;
- task queue;
- state mutations;
- output artifacts;
- completion predicate;
- transition prerequisites;
- allowed score changes;
- event types.

### Phase `PROMPT.md`

Contains only the current cognitive assignment. It must not repeat all permanent role documentation.

## R2.4 Persistent author role

The author is one persistent coordinator:

```text
Author Coordinator
├── Rebuttal Ralph Loop
└── Final Follow-Up Ralph Loop
```

Design-time directory:

```text
roles/author/
├── PRD.md
├── ROLE_SPEC.md
├── PROMPT.base.md
├── schemas/
│   ├── response-matrix.schema.json
│   ├── rebuttal.schema.json
│   └── final-followup.schema.json
├── workers/
│   └── response-draft-worker/
│       ├── SPEC.md
│       └── PROMPT.md
└── phases/
    ├── rebuttal/
    │   ├── SPEC.md
    │   ├── PROMPT.md
    │   └── tasks.template.json
    └── final-followup/
        ├── SPEC.md
        ├── PROMPT.md
        └── tasks.template.json
```

Per-review response workers are transient drafting helpers. They do not become separate authors and cannot publish directly. The author coordinator owns:

- evidence boundary;
- response matrix;
- cross-review consistency;
- commitments;
- admitted limitations;
- all published responses.

## R2.5 Persistent Area Chair role

The AC is one identity from assignment validation through meta-review:

```text
Area Chair
├── Reviewer Coverage Ralph Loop
├── Review Quality Check Ralph Loop
├── Discussion Moderation Ralph Loop
└── Meta-Review Ralph Loop
```

Design-time directory:

```text
roles/ac/
├── PRD.md
├── ROLE_SPEC.md
├── PROMPT.base.md
├── schemas/
│   ├── coverage-report.schema.json
│   ├── review-quality.schema.json
│   ├── discussion-issue.schema.json
│   └── meta-review.schema.json
└── phases/
    ├── reviewer-coverage/
    ├── review-quality-check/
    ├── discussion-moderation/
    └── meta-review/
```

Each phase directory contains `SPEC.md`, `PROMPT.md`, and `tasks.template.json`.

The AC’s state persists:

- assigned paper;
- reviewer panel and coverage assessment;
- review-quality judgments;
- issue ledger;
- discussion summaries;
- weighting of reviewer expertise and confidence;
- final recommendation.

## R2.6 SAC and PC roles

SAC and PC are also persistent roles, but they initially have fewer phases.

```text
roles/sac/
├── PRD.md
├── ROLE_SPEC.md
├── PROMPT.base.md
└── phases/
    └── calibration/
        ├── SPEC.md
        ├── PROMPT.md
        └── tasks.template.json

roles/pc/
├── PRD.md
├── ROLE_SPEC.md
├── PROMPT.base.md
└── phases/
    └── finalization/
        ├── SPEC.md
        ├── PROMPT.md
        └── tasks.template.json
```

Batch mode may later add SAC/PC phases for cohort calibration and Spotlight selection.

## R2.7 Validator role lifecycle

A validator with several distinct tasks should also use one persistent role and phase-specific loops.

Examples:

```text
roles/validators/mathematics/
├── PRD.md
├── ROLE_SPEC.md
├── PROMPT.base.md
└── phases/
    ├── claim-extraction/
    ├── assumption-audit/
    ├── symbolic-validation/
    ├── counterexample-search/
    ├── formalization/
    ├── confirmation/
    └── bundle-publication/
```

```text
roles/validators/code/
├── PRD.md
├── ROLE_SPEC.md
├── PROMPT.base.md
└── phases/
    ├── official-reproduction/
    ├── clean-room-reimplementation/
    ├── conformance-comparison/
    └── bundle-publication/
```

A validator may use subordinate workers internally, but the coordinator identity remains stable and owns the final finding ledger.

## R2.8 Runtime reviewer workspace

```text
runs/{run_id}/agents/reviewer-r2/
├── identity.json
├── persona.json
├── role-state.json
├── allowed-inputs.json
├── concern-ledger.json
├── question-ledger.json
├── score-history.json
├── literature-registry.json
├── progress.md
├── events.ndjson
├── phases/
│   ├── initial-review/
│   │   ├── state.json
│   │   ├── tasks.json
│   │   ├── progress.md
│   │   └── artifacts/
│   ├── followup/
│   ├── discussion/
│   └── final-justification/
└── published/
    ├── official-review.json
    ├── reviewer-followup.json
    ├── discussion-positions/
    └── final-review.json
```

Role state persists. Phase state is reset or initialized when a new phase begins.

## R2.9 Role and phase state

Role state example:

```json
{
  "agent_id": "reviewer-r2",
  "role": "reviewer",
  "persona_version": 1,
  "current_phase": "followup",
  "completed_phases": ["initial-review"],
  "official_review_version": 1,
  "current_review_version": 1,
  "score_history_version": 1,
  "concern_ledger_version": 1,
  "status": "running"
}
```

Phase state example:

```json
{
  "phase": "followup",
  "status": "running",
  "current_task": "classify-concern-resolution",
  "attempt": 2,
  "allowed_input_manifest_hash": "sha256:...",
  "last_artifact_hash": "sha256:...",
  "no_progress_count": 0
}
```

## R2.10 Phase transition gates

### Reviewer

```text
initial-review
  requires: persona frozen, paper frozen
  produces: official review and concern ledger

followup
  requires: official review published, associated rebuttal published
  produces: resolution ledger, score update, reviewer follow-up

discussion
  requires: author final round closed, AC issue opened
  produces: issue-specific positions and possible score update

final-justification
  requires: AC closes discussion input
  produces: immutable final review state
```

### Author

```text
rebuttal
  requires: initial-review freeze
  produces: one rebuttal per official review

final-followup
  requires: reviewer follow-ups published
  produces: one final response per applicable reviewer
```

### AC

```text
reviewer-coverage
  requires: personas proposed

review-quality-check
  requires: official reviews published

discussion-moderation
  requires: author–reviewer rounds sufficiently complete

meta-review
  requires: decisive issues closed or disputed
```

## R2.11 Phase-specific visibility matrix

| Role/phase | Own private state | Paper | Validation | Other reviews | Author response | Internal discussion |
|---|---:|---:|---:|---:|---:|---:|
| Reviewer / initial | Yes | Yes | Published bundle only | No | No | No |
| Reviewer / follow-up | Yes | Yes | Yes | No by default | Own thread | No |
| Reviewer / discussion | Yes | Yes | Yes | Yes | Yes | AC issues |
| Reviewer / final | Yes | Yes | Yes | Yes | Yes | Yes |
| Author / rebuttal | Yes | Yes | Author-visible | All official reviews | N/A | No |
| Author / final | Yes | Yes | Author-visible | Follow-ups | Prior responses | No |
| AC / quality | Yes | Yes | Yes | Yes | Published | No/private prep |
| AC / discussion | Yes | Yes | Yes | Yes | Yes | Full |
| SAC | Yes | As needed | Yes | Yes | Yes | Full record |
| PC | Yes | As needed | Yes | Yes | Yes | Final record |

The exact manifest is generated per phase and hashed.

## R2.12 Prompt composition per phase

Reviewer R2 follow-up invocation:

```text
shared/COMMON_AGENT_POLICY.md
+ shared/ICML_2026_REVIEW_RUBRIC.md
+ roles/reviewer/PROMPT.base.md
+ roles/reviewer/phases/followup/PROMPT.md
+ runs/{run_id}/agents/reviewer-r2/persona.json
+ runs/{run_id}/agents/reviewer-r2/concern-ledger.json
+ runs/{run_id}/agents/reviewer-r2/published/official-review.json
+ runs/{run_id}/agents/author/published/rebuttal-r2.json
+ current-task-context.json
+ roles/reviewer/schemas/followup.schema.json
```

The runner should not inject the entire PRD into every invocation. PRD is a product/design source of truth; `PROMPT.base.md` and the phase prompt are the model-facing compact instructions.

## R2.13 Event naming

Events include role and phase:

```text
reviewer.initial_review.task_started
reviewer.initial_review.artifact_published
reviewer.followup.score_changed
reviewer.discussion.position_published
reviewer.final_justification.completed

author.rebuttal.published
author.final_followup.published

ac.reviewer_coverage.completed
ac.review_quality.flagged
ac.discussion.issue_opened
ac.meta_review.published
```

## R2.14 Database implications

`agents` stores the persistent logical identity.

Add:

```text
agent_phase_runs
---------------
id
agent_id
run_id
phase
status
attempt_count
started_at
completed_at
input_manifest_hash
last_artifact_id
```

`score_history`, concern ledgers, discussion positions, and notes remain attached to the persistent reviewer ID.

Do not create a new `agents` record for Reviewer R2 follow-up or discussion.

## R2.15 Migration from the initial specification

Replace these separate design-time agents:

```text
initial-reviewer
reviewer-followup-agent
```

with:

```text
roles/reviewer/
  phases/initial-review/
  phases/followup/
  phases/discussion/
  phases/final-justification/
```

Replace:

```text
author-rebuttal-coordinator
author-final-followup-agent
```

with one persistent:

```text
roles/author/
  phases/rebuttal/
  phases/final-followup/
```

Replace:

```text
ac-discussion-moderator
ac-meta-review-agent
```

with one persistent:

```text
roles/ac/
  phases/reviewer-coverage/
  phases/review-quality-check/
  phases/discussion-moderation/
  phases/meta-review/
```

Existing prompt content and schemas should be moved into the appropriate phase directory rather than discarded.

---

# Coding Session Handoff

# Coding Session Update — Persistent Roles and Phase-Specific Ralph Loops

You are continuing an implementation that was started from the initial Ralph Review Agent System specification.

Treat this message and `RALPH_REVIEW_AGENT_SYSTEM_PLAN_AND_TECHNICAL_SPEC_V2.md` as an **authoritative architecture update**. Do not restart the project, discard working code, or rewrite unrelated subsystems. Inspect the current repository first, identify what has already been implemented, and migrate incrementally.

## Core correction

The initial spec may represent these as separate logical agents:

- initial reviewer;
- reviewer follow-up agent;
- reviewer debate agent;
- author rebuttal agent;
- author final-follow-up agent;
- AC discussion moderator;
- AC meta-review agent.

That model is superseded.

Use **persistent logical roles with phase-specific Ralph loops**:

```text
Reviewer R2
├── initial-review
├── followup
├── discussion
└── final-justification

Author Coordinator
├── rebuttal
└── final-followup

Area Chair
├── reviewer-coverage
├── review-quality-check
├── discussion-moderation
└── meta-review
```

A model process may restart every Ralph iteration, but the logical role identity persists through stable state, persona, ledgers, history, and workspace.

## Required design-time structure

Implement or migrate toward:

```text
roles/reviewer/
├── PRD.md
├── ROLE_SPEC.md
├── PROMPT.base.md
├── schemas/
└── phases/
    ├── initial-review/
    │   ├── SPEC.md
    │   ├── PROMPT.md
    │   └── tasks.template.json
    ├── followup/
    ├── discussion/
    └── final-justification/

roles/author/
├── PRD.md
├── ROLE_SPEC.md
├── PROMPT.base.md
├── workers/response-draft-worker/
└── phases/
    ├── rebuttal/
    └── final-followup/

roles/ac/
├── PRD.md
├── ROLE_SPEC.md
├── PROMPT.base.md
└── phases/
    ├── reviewer-coverage/
    ├── review-quality-check/
    ├── discussion-moderation/
    └── meta-review/
```

SAC and PC remain persistent roles with calibration and finalization phases. Multi-step validators should follow the same role/base-prompt/phase pattern.

## Runtime structure

A reviewer runtime workspace must resemble:

```text
runs/{run_id}/agents/reviewer-r2/
├── identity.json
├── persona.json
├── role-state.json
├── concern-ledger.json
├── question-ledger.json
├── score-history.json
├── literature-registry.json
├── progress.md
├── events.ndjson
├── phases/
│   ├── initial-review/
│   ├── followup/
│   ├── discussion/
│   └── final-justification/
└── published/
```

Do not create a new logical `agents` row for R2 follow-up or R2 discussion.

## State model changes

Add or implement:

- persistent `role-state`;
- nested `phase-state`;
- per-phase `allowed-inputs.json`;
- concern ledger;
- question ledger;
- score history;
- phase completion history;
- immutable official-review version;
- immutable final-review version.

Suggested database table:

```text
agent_phase_runs
---------------
id
agent_id
run_id
phase
status
attempt_count
started_at
completed_at
input_manifest_hash
last_artifact_id
```

The existing `agents` table represents logical identities.

## Permission changes by phase

Enforce phase permissions mechanically.

### Reviewer initial review

Can read paper, supplement, own persona, rubric, admissible literature, and published validation bundle.

Cannot read other reviews, other personas, author responses, AC opinion, or benchmark outcome.

### Reviewer follow-up

Can additionally read its own review, concern ledger, associated rebuttal, and published validation updates.

Cannot read other reviewer reviews by default.

### Reviewer discussion

Can read all published reviews, published author responses, AC issue threads, issue-specific reviewer positions, and validation evidence.

### Reviewer final justification

Can read the full permitted process record and freeze its final review.

Generate and hash `allowed-inputs.json` for every phase invocation.

## Prompt composition

Render prompts from modules:

```text
COMMON_AGENT_POLICY
+ ICML_RUBRIC
+ ROLE PROMPT.base.md
+ PHASE PROMPT.md
+ persona.json
+ persistent ledgers/history
+ task-context.json
+ output schema
```

Do not inject the full PRD into every model call.

## Migration rules

1. Inspect current files and preserve working implementation.
2. Move existing initial-reviewer prompt/spec content into `roles/reviewer/phases/initial-review`.
3. Move reviewer-follow-up content into `roles/reviewer/phases/followup`.
4. Create reviewer discussion and final-justification phase modules.
5. Merge author rebuttal and final-follow-up logical identities into one author coordinator.
6. Merge AC discussion and AC meta-review logical identities into one AC role.
7. Preserve existing schemas; rename or adapt them rather than deleting useful contracts.
8. Add compatibility adapters if current runtime code expects old role names.
9. Migrate state without losing existing test fixtures.
10. Update documentation and event names.

## Event changes

Use phase-qualified events:

```text
reviewer.initial_review.task_started
reviewer.initial_review.artifact_published
reviewer.followup.score_changed
reviewer.discussion.position_published
reviewer.final_justification.completed
author.rebuttal.published
author.final_followup.published
ac.discussion.issue_opened
ac.meta_review.published
```

## Required tests

Add tests proving:

1. Reviewer R2 has the same logical ID across all phases.
2. Persona and score history persist across process restarts.
3. Initial-review phase cannot access another reviewer’s artifacts.
4. Follow-up phase cannot access all reviews.
5. Discussion phase gains only the specified published inputs.
6. A phase cannot start before its transition gate passes.
7. A promise token cannot complete a phase without schema-valid artifacts.
8. Score changes append history rather than overwrite it.
9. Author response workers cannot publish directly.
10. AC state persists from coverage to meta-review.
11. Database projection creates one agent and multiple phase-run rows.
12. Old state and prompt paths migrate or remain backward compatible.

## Acceptance criteria

The migration is complete when:

- persistent roles and phase modules exist;
- reviewer, author, and AC identity continuity is enforced;
- per-phase input manifests are enforced;
- watchdog launches phases for an existing logical role;
- state schemas validate;
- existing functionality still works;
- all new and old tests pass;
- documentation reflects the new architecture;
- no duplicate logical reviewer identities are created for later phases.

## Work protocol

- Read the current repository and initial spec before editing.
- Write a migration plan to the project progress file.
- Implement in coherent vertical slices.
- Run formatting, type checks, unit tests, integration tests, and schema validation after each slice.
- Preserve existing work and commit meaningful checkpoints.
- Report what changed, tests run, and remaining blockers.
