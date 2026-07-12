# STATUS W2 H-AUTHOR

## State

Done in recovered Lane H.

## Implemented

- Persistent `author-coordinator` runtime in `roles/author/runtime.py` with one logical identity across `rebuttal` and `final-followup`.
- Coordinator-owned persistent response matrix, commitments, admitted limitations, official-review subscription inbox, and reviewer-followup inbox.
- Arrival-order polling and independent thread settlement for reviews published at different times.
- Transient per-review response workers under `roles/author/workers/response-draft-worker/`; workers receive no `identity.json`, declare `publisher_capability: false`, and cannot publish through either the runtime or checker.
- Immutable coordinator-only rebuttal and final-followup publication with one artifact per applicable reviewer.
- Rebuttal and final-followup phase modules, frozen-schema-valid task queues, role prompts, and author-specific schemas.
- Executable checker in `roles/author/checker.py` enforcing:
  - complete weakness and key-question response coverage;
  - allowed response labels and response-matrix agreement;
  - evidence-catalog boundaries;
  - rejection of invented experiments/results, citations, proofs, and implementation behavior;
  - professional tone;
  - cross-thread commitment consistency;
  - final-followup answers limited to newly raised questions;
  - persistent commitments and limitations carried into the final response.

## Fake-agent gates

`tests/test_author_system.py` covers:

- reviews arriving out of order and being claimed by arrival timestamp;
- thread settlement and one-published-response-per-review phase completion;
- worker draft transience and worker publication rejection;
- immutable coordinator publication;
- one coordinator identity across both phases;
- response matrix and commitments persisting across the phase transition;
- invented post-submission experiment/result rejection;
- invented citation rejection;
- contradiction between two reviewer-thread commitments;
- old-question and dropped-commitment rejection in final follow-up;
- phase visibility manifests and phase-task schema validation.

Committed adversarial fixtures are under `tests/fixtures/author/fake-agents/`.

## Real paper 34584 round

INTEGRATE ran the persistent Author Coordinator against all four independently published paper-34584 reviews. The coordinator produced one shared evidence catalog, one cross-thread response matrix, and four reviewer-specific rebuttals through real Codex invocations. Every rebuttal passed complete weakness/question coverage, evidence-boundary, truthfulness, publisher-identity, and cross-thread consistency checks.

Artifacts are committed under:

- `tests/fixtures/author/34584/real-round/evidence-catalog.json`
- `tests/fixtures/author/34584/real-round/response-matrix.json`
- `tests/fixtures/author/34584/real-round/reviewer-r{1,2,3,4}/`

Each reviewer directory contains the immutable official review, rebuttal, reviewer follow-up, author final follow-up, and complete sequence-ordered thread. The reviewer follow-ups raised no new questions, so the final Author Coordinator artifacts publish no invented response text; they carry all prior commitments and admitted limitations forward exactly as required.

## Verification

- `uv run pytest tests/test_author_system.py tests/test_reviewer_system.py -q` → `18 passed`.
- `uv run pytest -q` → `148 passed`.
- `bun test` → `133 pass`, `8 skip`, `0 fail`.
- `uv run ruff check roles/author roles/reviewer tests/test_author_system.py tests/test_reviewer_system.py` → all checks passed.

## Integration notes

- Frozen `packages/contracts` schemas were not edited.
- Validator artifact contracts were promoted only through INTEGRATE-approved schema requests.
- Reviewer follow-up generation remains owned by CF; Author Coordinator publication remains coordinator-only.
- The real threads are projected by M2 run `m2-34584` and rendered by the PostgreSQL-backed K2 viewer.
