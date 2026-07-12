# Charter W2 K2-VIEWER-LIVE — live viewer wiring

Spec: §23 (live path, SSE), §22 (NOTIFY), §28.K. Depends on: W1-K skeleton,
W1-J projector.

## Owns
`apps/viewer/` (live data layer), `tests/fixtures/viewer-live/`.

## Deliverables
1. Swap fixture adapter → packages/db snapshot queries.
2. SSE live path: Postgres NOTIFY → SSE route → EventSource; event IDs =
   per-run sequence; `Last-Event-ID` reconnect replays missed durable
   events before resuming live (§23).
3. `/runs/{runId}/process`: live agent states (§19.4 heartbeats, current
   task, attempts, no-progress counters), per-agent phase timeline from
   agent_phase_runs (one persistent identity, multiple phase rows — R2.14),
   phase machine visualization, budget consumption.
4. `/runs/{runId}/evidence`: validator findings with anchor deep-links into
   rendered paper.md; `/runs/{runId}/discussion`: AC issue threads.
5. Audit page: event history, hashes, decision provenance, §30 export.

## Done when
- Live E2E: replaying W0's sample-run event log through the projector while
  the viewer is open updates the forum feed within 2s without refresh.
- SSE reconnect test: kill connection mid-replay, reconnect with
  Last-Event-ID, no gaps or duplicates rendered.
- Playwright suite covers live update + reconnect.
- STATUS.md written.
