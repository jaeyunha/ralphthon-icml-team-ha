# STATUS W2 K2-VIEWER-LIVE

## Result

**PASS.** The viewer now uses `packages/db` snapshot queries whenever `DATABASE_URL` is configured, streams durable PostgreSQL events through SSE, refreshes the browser through `EventSource`, replays from `Last-Event-ID`, renders the required live pages, deep-links validation anchors into escaped `paper.md`, and exports the complete audit snapshot.

## Delivered behavior

### PostgreSQL data source

`apps/viewer/src/lib/viewer-db.ts` implements `ViewerDataSource` with the existing `@ralphthon/db/snapshots` read models:

- run list and detail from `listRunSnapshots` / `getAuditExportSnapshot`;
- forum notes from `getForumFeedSnapshot`;
- logical agents, multiple `agent_phase_runs`, execution attempts, cursors, and budget state from `getProcessStateSnapshot`;
- sequence-ordered durable events, artifacts, discussion issues, and decisions from `getAuditExportSnapshot`;
- hash-verified local artifact reads constrained to `VIEWER_ARTIFACT_ROOT`.

The fixture adapter remains an explicit/no-database development mode; database mode is selected whenever `DATABASE_URL` is present or `VIEWER_DATA_SOURCE=database` is set. The viewer remains read-only.

### Durable NOTIFY → SSE → EventSource path

- `viewer-live.ts` opens a dedicated PostgreSQL `LISTEN run_events` connection. NOTIFY payloads are treated only as wake-up signals.
- Each wake-up drains the durable `events` table strictly after the current per-run sequence.
- The listener is established before initial replay, closing the replay/listen race.
- SSE `id` values equal per-run event sequences and all browser events use the `run-event` type with the durable envelope in `data`.
- The browser keeps its initial cursor stable across React server refreshes, deduplicates sequence IDs, and lets native `EventSource` reconnect with `Last-Event-ID`.
- Forced two-event connection closures produced server replay cursors `1 → 3 → 5` and rendered `[2,3,4,5,6]` exactly once with no gaps.
- The under-two-second forum update is emitted by the real `NdjsonProjector`, `PostgresProjectionStore`, `projectCoreReadModels`, and W0 event adapter: one W0 envelope was inserted, projected to a note, and notified before the viewer refreshed.

### Pages and export

- Forum: live status, sequence log, and automatic expansion of newly published replies.
- Process: persistent logical agent card, current task, heartbeat, attempt, no-progress count, last artifact hash, per-phase timeline, and budget consumption.
- Evidence: schema-valid validator artifacts and stable anchor links.
- Paper: escaped `paper.md` lines with stable DOM anchors; no raw HTML execution.
- Discussion: issue-based AC thread records, participants, positions, evidence links, and resolution.
- Audit: durable event timeline, state/input hashes, projected sequence, artifact inventory, and downloadable JSON export at `/api/runs/{runId}/audit/export`.

### Security and integrity

Artifact paths must remain beneath `VIEWER_ARTIFACT_ROOT`; bodies are SHA-256 verified before serving. Database-provided filenames and media types are rejected if unsafe for response headers. API route policy remains GET-only and includes the audit export.

### Integration resolution

INTEGRATE removed the test-only projector wrapper and added an explicit `serializeJsonParameters` option to `createPostgresJsPool` for postgres-js clients shared with Drizzle. The default raw-postgres path preserves typed JSON parameters; the Drizzle-backed viewer test path serializes plain JSON objects before `$n::jsonb` binding. Unit tests cover both modes, the raw PostgreSQL projector contract passes, and both live Playwright suites use the production adapter.

## Verification

Passed on PostgreSQL 16 on 2026-07-11:

```text
TEST_DATABASE_URL=postgres://ralph:ralph@127.0.0.1:55439/ralph_review \
  bun test packages/db/test/database.test.ts
4 passed, 0 failed

DATABASE_URL=postgres://ralph:ralph@127.0.0.1:55439/ralph_review \
VIEWER_DATA_SOURCE=database \
VIEWER_ARTIFACT_ROOT=/Users/jaeyunha/dev/ralphthon-icml \
VIEWER_SSE_MAX_EVENTS=2 \
  bun x playwright test tests/e2e/live-viewer.e2e.ts --project=chromium
3 passed (13.0s)
  live forum update case: explicit <2000ms assertion passed
  production projector result: inserted=1, notified=1, caught_up=true
  reconnect case: cursors 1,3,5; rendered 2,3,4,5,6; zero gaps/duplicates

DATABASE_URL=postgres://ralph:ralph@127.0.0.1:55439/ralph_review \
VIEWER_DATA_SOURCE=database \
VIEWER_ARTIFACT_ROOT=/Users/jaeyunha/dev/ralphthon-icml \
VIEWER_SSE_MAX_EVENTS=20 \
  bun x playwright test tests/e2e/m2-live-viewer.e2e.ts --project=chromium
2 passed (12.3s)
  projected 93 durable real-paper events, 16 notes, 21 artifacts, 8 score rows, and 17 phase rows
  live append sequence 94 appeared through PostgreSQL NOTIFY without refresh in under 2 seconds

VIEWER_DATA_SOURCE=fixture \
  bun x playwright test tests/e2e/viewer.e2e.ts --project=chromium
7 passed (4.3s)

bun run typecheck
passed

bun run test
22 passed, 0 failed

bun run build
compiled, typechecked, and generated all viewer/API routes successfully
```

Structured evidence is committed in `tests/fixtures/viewer-live/verification.json`; database seed artifacts are under `tests/fixtures/viewer-live/run-live-1/`.
