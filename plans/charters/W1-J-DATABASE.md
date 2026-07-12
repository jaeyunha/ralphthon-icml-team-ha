# Charter W1 J-DATABASE — PostgreSQL, Drizzle, projector, events

Spec: §22 (database + event architecture), §28.J, PHASED_ROLE_ARCHITECTURE
R2.13 (phase-qualified event names) + R2.14 (agents = logical identities,
agent_phase_runs = phase executions).

## Owns
`packages/db/`, `engine/projector/`, `migrations/`, `docker-compose.yml`
(postgres service), `tests/fixtures/db/`.

## Deliverables
1. Drizzle schema for §22.3 + R2.14 tables: runs, agents (LOGICAL
   identities only — never a row per phase), **agent_phase_runs** (id,
   agent_id, run_id, phase, status, attempt_count, started_at,
   completed_at, input_manifest_hash, last_artifact_id), events
   (`UNIQUE(run_id, sequence)` + globally unique event id; phase-qualified
   type names per R2.13), notes (parent/thread ids for the OpenReview
   reply tree), score_history (append-only, attached to persistent
   reviewer id), artifacts, discussion_issues, execution_jobs, decisions.
   Migrations under `migrations/`.
2. Projector (TS, Bun): tails `runs/<id>/events.ndjson`, idempotent inserts
   (replay-safe), read-model projections, `NOTIFY` after commit, crash
   recovery via durable cursor. Agents never write to Postgres (§22.2) —
   only the projector does.
3. Event emission helper used by the watchdog: append to events.ndjson with
   monotonic per-run sequence (uses packages/contracts allocator).
4. Snapshot query module for the viewer: run list, forum feed, process
   state, score history, audit export.

## Done when
- `docker compose up -d postgres && bun run db:migrate` clean.
- Projector contract tests: idempotent double-replay, out-of-order file
  writes, crash mid-batch + restart without loss or duplication, NOTIFY
  fired per committed event.
- Feeding W0's sample-run fixture event log produces correct projections
  (golden snapshot test).
- Projection test: one logical reviewer with three completed phases yields
  ONE agents row + THREE agent_phase_runs rows (R2.14).
- STATUS.md written.
