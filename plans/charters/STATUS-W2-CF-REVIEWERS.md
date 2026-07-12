# STATUS W2 CF-REVIEWERS

## State

Done. Lane CF implements the persona compiler, persistent reviewer role and all four phase modules, executable review checker, runtime continuity and append-only history helpers, real paper fixtures, and tests. No files under frozen `packages/contracts` or `packages/schemas` were changed.

## Deliverables

- `engine/loops/persona-compiler/persona_compiler.py`
  - classifies the paper domain;
  - compiles four differentiated, schema-valid personas;
  - derives explicit theorem, claim, empirical, categorical, literature, reproducibility, and cross-domain deep-audit assignments;
  - adds a fifth reviewer when a required specialty is uncovered;
  - rejects duplicate panels, shared blind spots, schema violations, and encoded verdict/harshness;
  - runs an optional mandatory-failure semantic judge command with no fallback.
- `roles/reviewer/`
  - design-only PRD, permanent role invariants, stable model prompt, mirrored role-local schemas;
  - initial-review, followup, discussion, and final-justification SPEC/PROMPT/task queues;
  - `runtime.py` for frozen identity/persona continuity, one-task queue discipline, immutable publication, phase transitions, and hash-chained score history;
  - `checker.py` for schema, resolving anchors, abstract-copy, score/prose, confidence/depth, ledger, and visibility checks with exact reopen feedback;
  - `run_initial_review.py` for the real Codex-driven twelve-task initial-review queue.
- `tests/fixtures/reviewers/34584/`
  - four-person panel with a completed real Codex semantic judge;
  - real Codex official review v1 with seven anchored concerns;
  - matching concern/question ledgers, role state, task queue, initial manifest, and append-only score histories;
  - bounded rebuttal input and reviewer follow-up covering every original concern without inventing new evidence;
  - structured real-run evidence containing all twelve task artifact hashes and manifest hashes.

## Real-tool and real-paper evidence

Paper: extraction golden fixture `34584`, bound to source PDF SHA-256 `7de57c5f431ee13df26d2dd14154b1f0621db001222336bf1a3acce17f13a82a`.

Persona semantic gate:

```text
uv run python engine/loops/persona-compiler/persona_compiler.py compile \
  --dossier tests/fixtures/extraction/34584/paper-dossier.json \
  --paper-id 34584 \
  --persona-schema packages/schemas/schemas/persona.schema.json \
  --judge-command 'codex exec --dangerously-bypass-approvals-and-sandbox -' \
  --output tests/fixtures/reviewers/34584/personas.json
```

Result: passed with four complementary personas and no judge rejection.

Initial review:

```text
uv run python roles/reviewer/run_initial_review.py \
  --run-dir /tmp/reviewer-real-34584-worker1 \
  --team-name implement-the-six-w2-lanes-and-23a7fd58 \
  --worker-id worker-1
```

Observed tool: `codex-cli 0.144.1`; production command: `codex exec --dangerously-bypass-approvals-and-sandbox -`. All twelve §13.3 tasks completed through the real agent loop. The self-audit reopened until the executable checker passed. Final official-review hash: `sha256:c6d1c38694a14f8f0fcdb91a08aad46026cf9fc08a3ed42325c210ce17544d89`. `real-run-evidence.json` records task attempts, timestamps, artifact hashes, and the hash-verified isolation manifest.

The final initial-review manifest has `other_reviews=no`, `author_response=no`, and `internal_discussion=no`; it exposes only the frozen paper, published validation/broker evidence, own private state, persona, policy, rubric, prompts, task context, and schema.

## Integrated four-reviewer M2 round

INTEGRATE additionally ran four isolated Codex initial-review invocations and four isolated follow-up invocations against paper 34584. Each reviewer used only its own frozen persona, official review, concern ledger, associated rebuttal, and paper anchors. The committed artifacts are under `tests/fixtures/reviewers/34584/reviewer-r{1,2,3,4}/`.

All four official reviews passed the executable checker after the Reynolds-averaging false-positive regression was fixed. All four follow-ups validate, cover every immutable weakness ID exactly once, use only the allowed resolution statuses, preserve reviewer identity, and append explicit changed-or-unchanged score rationale. No reviewer raised a new question. The combined reviewer/author gate suite passes 18 tests.

## Executed gates

```text
uv run pytest tests/test_reviewer_system.py tests/test_author_system.py -q
18 passed

uv run ruff check engine/loops/persona-compiler/persona_compiler.py \
  roles/reviewer roles/author tests/test_reviewer_system.py \
  tests/test_author_system.py
All checks passed!

uv run pytest -q
148 passed

bun test
133 pass, 8 skip, 0 fail
```

Tests cover duplicate rejection, verdict leakage, fifth-reviewer coverage repair, queue reopen behavior, all-phase identity/persona continuity, visibility-manifest enforcement, append-only score history, immutable fixture schemas, exact concern coverage, resolving anchors, and the real-run evidence contract.

## Integration notes

- The original single-reviewer fixture remains as a focused role-loop contract test.
- The M2 real round uses stable reviewer-r1 through reviewer-r4 identities and committed per-reviewer official-review, concern-ledger, and follow-up artifacts.
- The role-local schemas mirror frozen W0 contracts where applicable; validator schema changes were routed through INTEGRATE.
