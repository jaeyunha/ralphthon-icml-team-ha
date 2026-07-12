# M2 Result — full reviewer round, rebuttal, persistence, and live viewer

**Result: PASS**

Executed from integrated `main` on 2026-07-11 against the real paper:

`2026_icml_paper_to_benchmark/34584_Foundations_of_Equivaria.pdf`

The run preserves the M1 freeze hash:

`sha256:ed2d96371561100ff9243590a7a575a9197aa54d9fa8c9bd94fa8e77df755cf7`

## W2 lane integration

| Lane | Integrated evidence |
|---|---|
| W2-CF-REVIEWERS | `d46c65e`; persona compiler, persistent reviewer phases, checker, real Codex review fixture, and status report |
| W2-G1-CODEVAL | `18f91bc`; rootless Docker reproduction, clean-room/conformance framework, and real execution gates |
| W2-G2-MATHVAL | `7ba5fde`, `eba2681`; symbolic, SMT, numerical, shape, equation-to-code, and Lean evidence for paper 34584 |
| W2-G3-STATREF | `475d664`, `2410d3d`; statistics, references, ethics, arbitration, and frozen validation bundle |
| W2-H-AUTHOR | `ef604f3`; persistent Author Coordinator, transient non-publishing workers, truthfulness and consistency gates |
| W2-K2-VIEWER-LIVE | `e365dc9`, `61b95e0`; PostgreSQL snapshots, durable SSE replay, real-run viewer projection, and live Playwright coverage |
| Frozen validator schemas | `8c47209`; approved strict validator artifact contracts and fixtures |

Every lane has a committed status report under `plans/charters/`.

## Real paper 34584 review loop

Four independent Codex reviewer invocations used separately frozen personas and could not read peer reviews during the initial-review or follow-up phases. The immutable initial artifacts are under:

`tests/fixtures/reviewers/34584/reviewer-r{1,2,3,4}/`

The persistent Author Coordinator produced a shared response matrix and four evidence-bounded rebuttals. All rebuttals passed the author truthfulness, coverage, evidence-boundary, publisher-identity, and cross-thread consistency gates. The complete committed threads are under:

`tests/fixtures/author/34584/real-round/`

| Reviewer | Initial axes S/P/Si/O | Initial overall/confidence | Follow-up axes S/P/Si/O | Follow-up overall/confidence | Concern resolutions |
|---|---:|---:|---:|---:|---:|
| reviewer-r1 | 2/3/2/2 | 3/4 | 3/3/2/2 | 3/4 | 5 |
| reviewer-r2 | 2/2/2/2 | 3/4 | 3/3/2/2 | 3/4 | 4 |
| reviewer-r3 | 3/2/3/2 | 3/3 | 3/3/3/2 | 3/3 | 5 |
| reviewer-r4 | 2/2/2/2 | 3/3 | 2/2/2/2 | 3/3 | 4 |

All reviewers retained overall score 3 after rebuttal. Reviewers r1–r3 raised one or more axis scores because the response narrowed unsupported scope; reviewer-r4 kept every score unchanged because no corrected experiment, proof, efficiency study, or closest-work comparison was supplied. No reviewer raised a new follow-up question. The final Author Coordinator artifacts therefore contain no invented response content and carry all prior commitments and admitted limitations forward.

## Validator evidence supplied to the round

- Code validator: typed `not_executable` finding for paper 34584 because the frozen submission contains no executable implementation or reproducible environment.
- Mathematics validator: real paper-34584 claim inventory, symbolic/SMT/numerical/shape/equation-to-code checks, pinned Lean evidence, confirmation report, and published math bundle.
- Statistics/references/ethics/arbitration: frozen 43-finding validation bundle, including protocol-parity, subject-overlap, seed, uncertainty, multiplicity, validation-breadth, citation-identity, and ethics-trigger findings.
- The author evidence catalog and every rebuttal reference were checked against the frozen paper and validator artifacts.

## Durable projection and live viewer

The committed M2 event fixture is:

`tests/fixtures/m2/34584/events.ndjson`

It contains 93 sequence-contiguous, frozen-schema-valid durable events for run `m2-34584`. Projection through the production W0 adapter, `NdjsonProjector`, `PostgresProjectionStore`, core read models, PostgreSQL transaction, and `NOTIFY` path produced:

- 12 persistent logical agents;
- 17 phase-run rows;
- 93 durable base events;
- 16 published notes: 4 reviews, 4 rebuttals, 4 reviewer follow-ups, and 4 author final follow-ups;
- 8 score-history rows;
- 21 artifact rows.

The live M2 Playwright test opened the PostgreSQL-backed viewer, rendered all four review threads, persistent process timelines, real validator findings, paper anchors, and the audit export. Appending sequence 94 through the same projector made the new note visible without refresh in under two seconds.

The separate reconnect suite forced connection closure every two events. Native `EventSource` reconnects sent `Last-Event-ID`; server cursors were `1`, `3`, and `5`, and the browser rendered sequences `2,3,4,5,6` exactly once with no gaps or duplicates.

## Artifact validation

- `scripts/validate-run.sh tests/fixtures/m2/34584`: 95 documents validated.
- `scripts/validate-run.sh tests/fixtures/extraction/34584`: 11 documents validated.
- `scripts/validate-run.sh tests/fixtures/validators-math/34584/run`: 32 documents validated.
- Frozen statistics/reference/ethics/arbitration bundle: 1 document validated with 43 findings.
- Reviewer and author real-thread tests: 18 passed.
- Frozen schema suite: 27 passed.

## Integrated regression evidence

- Root Bun suite: 133 passed, 8 skipped, 0 failed.
- Root Python suite: 148 passed, 0 failed.
- Viewer: TypeScript passed, 22 unit/route tests passed, and production Next.js build passed.
- Live Playwright suites: 5 passed in one serial PostgreSQL run, covering K2 reconnect and M2 real-paper behavior.
- Fixture-backed Playwright regression: 7 passed.
- PostgreSQL database integration: 4 passed.
- PostgreSQL projector integration: 3 passed.
- Contracts, database, projector, viewer, schema generated types, and literature-broker TypeScript checks passed.
- W2-focused Ruff checks passed for validators, reviewer, author, and directly changed tests.

A repository-wide Ruff invocation also reports 241 pre-existing E701/E702 formatting findings in the W1 watchdog implementation and tests. They are unrelated to W2/M2 behavior and were not suppressed or rewritten during this integration.
