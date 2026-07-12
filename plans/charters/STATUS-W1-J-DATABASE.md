# STATUS W1-J-DATABASE

## State

**DONE — ready for INTEGRATE, with two cross-lane wiring notes below.**

The lane is rebased on current main (`2e28815`, including the passive viewer)
and imports the frozen `packages/contracts` allocator/assertions plus the
generated `packages/schemas` `EventEnvelope` type and JSON Schema without
modifying either frozen package.

## Delivered

- PostgreSQL 16 Docker Compose service and clean Drizzle migration for:
  `runs`, persistent logical `agents`, `agent_phase_runs`, globally
  idempotent `events`, OpenReview reply-tree `notes`, append-only
  `score_history`, `artifacts`, `discussion_issues`, `execution_jobs`,
  `decisions`, and durable `projection_cursors`.
- Event storage preserves the frozen W0 actor, artifact, causation, timestamp,
  and payload fields; enforces global event IDs, `UNIQUE(run_id, sequence)`,
  positive sequences, and exactly three phase-qualified event-type segments.
- W0-schema-valid event emitter and CLI using
  `packages/contracts` `EventSequenceAllocator`; a cross-process append guard
  serializes allocation plus fsynced NDJSON append per run.
- Bun projector tail loop and CLI for `runs/<run_id>/events.ndjson`, with
  transactional event/read-model/cursor writes, replay conflict detection,
  durable byte/sequence/event cursors, crash recovery, and one post-commit
  `run_events` notification per newly committed event.
- PostgreSQL adapter for the repository's `postgres.js` driver.
- Viewer snapshot queries for run list, forum feed, process state, score
  history, and complete audit export.
- W0-shaped deterministic DB fixtures and golden snapshots covering all ten
  core projection tables, duplicate replay, out-of-order rejection,
  crash/restart, notifications, and one reviewer identity across three phases.
- Root `bun.lock` was regenerated with `bun install` after the viewer rebase;
  it contains the viewer, database, and projector workspace dependencies.
- Database integration tests require explicit `TEST_DATABASE_URL`; root test
  discovery ignores generic `DATABASE_URL` and skips database suites safely.

## Verification

All commands passed on this branch:

- `bun install --frozen-lockfile` after resolving the viewer/database lock merge
- `bun run --cwd packages/db typecheck`
- `bun run --cwd engine/projector typecheck`
- `python3 tests/fixtures/db/validate_fixtures.py`
  - 36 canonical events, 6 crash events, 10 projections validated.
- Clean migration on an isolated port:
  - `POSTGRES_PORT=55439 docker compose down -v`
  - `POSTGRES_PORT=55439 docker compose up -d --wait postgres`
  - `DATABASE_URL=postgres://ralph:ralph@localhost:55439/ralph_review bun run --cwd packages/db db:migrate`
- Root suite without database credentials:
  - `env -u TEST_DATABASE_URL -u DATABASE_URL bun test`
  - 92 passed, 7 skipped, 0 failed.
- Explicit focused database suite:
  - `env -u DATABASE_URL TEST_DATABASE_URL=postgres://ralph:ralph@localhost:55439/ralph_review bun test packages/db/test/database.test.ts engine/projector/test/projector.test.ts engine/projector/test/postgres-projector.test.ts`
  - 16 passed, 0 failed.
- Generic URL isolation check:
  - `env -u TEST_DATABASE_URL DATABASE_URL=postgres://invalid:invalid@127.0.0.1:1/invalid bun test packages/db/test/database.test.ts`
  - 4 skipped, 0 failed; no connection was attempted.
- `uv run --frozen pytest`
  - 54 passed, 0 failed.
- `scripts/validate-run.sh tests/fixtures/contracts/sample-run`
  - 27 documents validated.
- Projector CLI one-shot smoke test passed against the canonical event log.
- `ralph-emit-event` CLI smoke test emitted a frozen W0 envelope with sequence 1.

## Integration notes / blockers

1. **Root migration alias:** the charter-owned package command is
   `bun run --cwd packages/db db:migrate`. The frozen W0 root `package.json`
   does not define a root `db:migrate` alias, and this lane did not edit that
   W0-owned manifest. INTEGRATE should add
   `"db:migrate": "bun run --cwd packages/db db:migrate"` if the exact
   repository-root shorthand is required.
2. **Watchdog callsite:** the current W1-D branch was observed emitting a
   legacy envelope without W0 `sequence`, `occurred_at`, `actor`, or `payload`
   fields. It must call `ralph-emit-event` or the exported `RunEventEmitter`
   after lane integration. The emitter contract and CLI are complete here.
3. Host port 5432 was occupied by an unrelated user PostgreSQL container, so
   verification used the supported `POSTGRES_PORT=55439` override. This is an
   environment-only condition, not a repository defect.

No database/projector implementation blocker remains in this lane.
