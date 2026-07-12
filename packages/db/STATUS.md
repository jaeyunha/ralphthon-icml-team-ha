# W1-J Database Package Status

## Implemented

- Drizzle PostgreSQL schema and initial migration for runs, persistent logical
  agents, `agent_phase_runs`, durable events, OpenReview reply-tree notes,
  append-only score history, artifacts, discussion issues, execution jobs,
  decisions, and durable projector cursors.
- Frozen W0 `EventEnvelope` mapping through `src/event-adapter.ts`, preserving
  actor, artifact, causation, timestamp, and payload fields.
- Event invariants: globally unique event ID, `UNIQUE(run_id, sequence)`,
  positive sequence, and exactly three phase-qualified type segments.
- Viewer snapshot queries for run list, forum feed, process state, score
  history, and audit export.
- PostgreSQL 16 Docker Compose service, package-local migration command, and
  focused integration tests.

## Integration boundary

- `packages/contracts` owns durable per-run sequence allocation and event-name
  assertions.
- `packages/schemas` owns the frozen event envelope and generated TypeScript
  type.
- Only `engine/projector` writes event and projection rows. Agents and watchdog
  processes append schema-valid events to the filesystem log.
- Root workspace script/lockfile wiring remains an INTEGRATE-owned change; the
  package command is `bun run --cwd packages/db db:migrate`.
