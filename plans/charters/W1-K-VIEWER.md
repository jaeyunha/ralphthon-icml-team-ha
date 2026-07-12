# Charter W1 K-VIEWER — passive Next.js viewer skeleton

Spec: §23 (passive viewer), §28.K. Strictly read-only: no start/stop/
control of loops, renders only validated published artifacts + committed DB
state (§26).

## Owns
`apps/viewer/`, `tests/fixtures/viewer/`.

## Deliverables
1. Next.js app (Bun) with §23 pages: `/` run list, `/runs/{runId}`
   OpenReview-style forum feed (threaded notes, review forms, score chips,
   decision banner), `/runs/{runId}/process`, `/runs/{runId}/discussion`,
   `/runs/{runId}/evidence`, `/runs/{runId}/audit`.
2. Read-only API routes per §23 (runs, notes, events, artifacts, snapshot).
   In W1, back them with a fixture adapter reading W0's sample-run tree;
   swap to packages/db snapshot queries at integration with J.
3. OpenReview-fidelity styling: review form fields and thread layout match
   the real ICML form (reference screenshots + §5.2 field list).
4. SSE route stub with Last-Event-ID replay contract (§23) — full live
   wiring is W2 (K2).

## Done when
- `bun run dev` renders all six pages from fixtures; forum feed shows a
  full thread (review → rebuttal → follow-up → final).
- Zero mutation endpoints exist (test asserts route table).
- Playwright smoke: navigate all pages, thread expansion, score rendering.
- STATUS.md written.
