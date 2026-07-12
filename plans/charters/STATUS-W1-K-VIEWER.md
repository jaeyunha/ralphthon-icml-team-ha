# W1 K-VIEWER Status

## State

**DONE — PASSIVE VIEWER GATES GREEN**

The viewer is fixture-backed, strictly read-only, rebased onto frozen W0 (`fb54a11`), and wired to `@ralph-review/contracts` plus `@ralph-review/schemas`. It validates durable event envelopes and immutable published review artifacts before rendering or serving them.

## Delivered

- Bun/Next.js App Router viewer under `apps/viewer/`.
- Six required pages:
  - `/`
  - `/runs/{runId}`
  - `/runs/{runId}/process`
  - `/runs/{runId}/discussion`
  - `/runs/{runId}/evidence`
  - `/runs/{runId}/audit`
- OpenReview-style forum with separate root threads, expandable reply chains, official ICML score fields, author rebuttal, reviewer follow-up, author final follow-up, reviewer final justification, meta-review, and decision banner.
- Exactly the seven §23 GET API routes for runs, notes, events, artifacts, snapshots, and SSE replay.
- SSE replay stub using per-run sequence IDs and `Last-Event-ID`, with no mutation or process-control endpoints.
- Typed fixture adapter with identifier/path/header safety checks, artifact SHA-256 verification, event ordering checks, and coherent snapshot checks.
- Frozen W0 integration:
  - `assertEventSequence`, `assertPhaseQualifiedEventType`, and `sha256Bytes` from `@ralph-review/contracts`.
  - AJV validation against exported W0 event-envelope, official-review, and final-review schemas.
  - Generated W0 TypeScript artifact types from `@ralph-review/schemas`.
- Golden viewer fixture under `tests/fixtures/viewer/icml-2026-0421/` with phase-qualified W0 event envelopes and schema-valid immutable official/final review artifacts.
- Exact route-table mutation audit plus Playwright smoke coverage for every page, thread expansion, and score rendering.
- Playwright discovery is explicitly limited to `tests/e2e/**/*.e2e.ts`, so repository-wide `bun test` cannot import Playwright suites.

## Verification

Executed after rebasing onto main/W0:

- `bun install --frozen-lockfile` at repository root — passed.
- `bun test` at repository root — 83 tests passed with 248 assertions; Playwright files were excluded from Bun discovery.
- `bun run check` in `apps/viewer` — passed:
  - TypeScript check passed.
  - 20 Bun tests passed with 46 assertions.
  - Next production build emitted all six pages and all seven GET API routes.
- `bun run test:e2e` in `apps/viewer` — 7 Playwright tests passed from the explicit `*.e2e.ts` suite.
- `bun run check` in `packages/contracts` — 39 tests passed with 136 assertions; TypeScript check passed.
- `bun run check:types && bun test` in `packages/schemas` — generated types had no drift; 24 tests passed with 66 assertions.
- `git diff --check` — passed.

## Integration notes

- The fixture data source is isolated behind `ViewerDataSource`; W2/J can replace it with committed database snapshot queries without changing page or API consumers.
- Published JSON artifacts with `official_review` or `final_review` kinds are rejected unless they satisfy frozen W0 schemas and their manifest SHA-256 digest.
- Durable events are stored in W0 snake-case envelope form and projected into the viewer model only after schema and role/phase event-name validation.
- The repository root `bun.lock` now contains the viewer workspace and dependencies; the obsolete app-local lockfile was removed to preserve one Bun workspace lock.
- No schema change request was needed. `packages/contracts/` and `packages/schemas/` were not modified.
- Full database-backed snapshot queries and live PostgreSQL/NOTIFY SSE streaming remain assigned to J and W2 K2 respectively.
