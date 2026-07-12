import { describe, expect, test } from "bun:test";

import {
  DeterministicProjectionErrorV2,
  NdjsonProjectorV2,
  ProjectionConflictErrorV2,
  ProjectionRetryableErrorV2,
  type ProjectionBatchV2,
  type ProjectionStoreV2,
  type ProjectionTransactionV2,
} from "../src";

const hash = (value: string) => `sha256:${value.padEnd(64, "0")}`;

function batch(eventId = "event-1"): ProjectionBatchV2 {
  const eventHash = hash("a");
  return {
    batchId: "00000000-0000-4000-8000-000000000001",
    runId: "run-v2",
    source: "events-v2.ndjson",
    durableTip: { schema_version: 2, log_dev: 1, log_ino: 2, end_offset: 100, last_sequence: 1, last_event_hash: eventHash },
    cursorAnchor: { byteOffset: 0, lastSequence: 0 },
    events: [{
      byteOffset: 0,
      envelope: {
        schema_version: 2, event_id: eventId, idempotency_key: `key-${eventId}`, run_id: "run-v2",
        sequence: 1, previous_event_hash: hash("0"), event_hash: eventHash,
        type: "reviewer.initial_review.task_started", occurred_at: "2026-07-12T00:00:00Z",
        actor: { agent_id: "reviewer", role: "reviewer", phase: "initial_review" }, payload: { task_id: eventId },
      },
      event: {
        id: eventId, runId: "run-v2", sequence: 1, type: "reviewer.initial_review.task_started",
        occurredAt: "2026-07-12T00:00:00Z", agentId: "reviewer", actorRole: "reviewer",
        phase: "initial_review", payload: { task_id: eventId },
      },
    }],
    nextCursor: {
      runId: "run-v2", source: "events-v2.ndjson", byteOffset: 100, lastSequence: 1,
      lastEventId: eventId, lastEventHash: eventHash, updatedAt: "2026-07-12T00:00:01Z",
      logDev: 1, logIno: 2, durableEndOffset: 100, durableLastSequence: 1, durableLastEventHash: eventHash,
    },
  };
}

class MemoryStore implements ProjectionStoreV2 {
  events = new Map<string, string>();
  cursors = new Map<string, string>();
  batches = new Map<string, string>();
  projections: string[] = [];
  publications: string[] = [];
  quarantines: string[] = [];
  failCommit = false;
  conflict = false;

  async loadCursorV2() { return undefined; }
  async transactionV2<T>(_runId: string, work: (tx: ProjectionTransactionV2) => Promise<T>): Promise<T> {
    const events = new Map(this.events); const cursors = new Map(this.cursors); const batches = new Map(this.batches);
    const projections = [...this.projections]; const publications = [...this.publications];
    const tx: ProjectionTransactionV2 = {
      persistCanonicalEnvelope: async (item) => {
        const existing = events.get(item.envelope.event_id);
        if (existing === undefined) { events.set(item.envelope.event_id, item.envelope.event_hash); return { status: "inserted" }; }
        return existing === item.envelope.event_hash ? { status: "duplicate" } : { status: "conflict" };
      },
      applyReadModelsV2: async (item) => { projections.push(item.event.id); },
      savePublicationRegistryRows: async (rows) => { publications.push(...rows.map((row) => row.publicationId)); },
      saveProjectionBatch: async (item) => { batches.set(item.batchId, item.nextCursor.lastEventHash ?? ""); },
      saveCursorV2: async (cursor) => { cursors.set(cursor.source, cursor.lastEventHash ?? ""); },
    };
    const result = await work(tx);
    if (this.failCommit) throw new Error("connection lost during COMMIT");
    this.events = events; this.cursors = cursors; this.batches = batches; this.projections = projections; this.publications = publications;
    return result;
  }
  async reconcileProjectionBatch(item: ProjectionBatchV2) {
    if (this.conflict) return "conflict" as const;
    return this.batches.get(item.batchId) === (item.nextCursor.lastEventHash ?? "") ? "committed" as const : "not_committed" as const;
  }
  async quarantineV2(input: { failureCode: string }) { this.quarantines.push(input.failureCode); }
}

describe("NdjsonProjectorV2", () => {
  test("atomically saves canonical event, read model, batch ledger, registry, and cursor", async () => {
    const store = new MemoryStore();
    const result = await new NdjsonProjectorV2(store, { publicationRows: (item) => [{ publicationKind: "note", publicationId: "note-1", eventId: item.event.id, eventHash: item.envelope.event_hash }] }).projectCapturedBatch(batch());
    expect(result).toMatchObject({ status: "committed", inserted: 1 });
    expect([...store.events.keys(), store.projections, store.publications, [...store.batches.keys()], [...store.cursors.keys()]]).toEqual(["event-1", ["event-1"], ["note-1"], ["00000000-0000-4000-8000-000000000001"], ["events-v2.ndjson"]]);
  });

  test("treats exact canonical retry as idempotent and surfaces immutable conflict", async () => {
    const store = new MemoryStore(); const projector = new NdjsonProjectorV2(store);
    await projector.projectCapturedBatch(batch());
    await expect(projector.projectCapturedBatch(batch())).resolves.toMatchObject({ duplicates: 1, inserted: 0 });
    const conflicting = batch(); conflicting.events[0]!.envelope.event_hash = hash("b");
    await expect(projector.projectCapturedBatch(conflicting)).rejects.toBeInstanceOf(ProjectionConflictErrorV2);
  });

  test("reconciles a commit whose connection outcome is unknown", async () => {
    const store = new MemoryStore(); store.failCommit = true;
    // Simulate the database having committed before the client lost its outcome.
    store.batches.set(batch().batchId, batch().nextCursor.lastEventHash!);
    await expect(new NdjsonProjectorV2(store).projectCapturedBatch(batch())).resolves.toMatchObject({ status: "committed" });
    store.batches.clear();
    await expect(new NdjsonProjectorV2(store).projectCapturedBatch(batch())).rejects.toBeInstanceOf(ProjectionRetryableErrorV2);
  });

  test("quarantines deterministic invalid input before any transaction state changes", async () => {
    const store = new MemoryStore();
    const projector = new NdjsonProjectorV2(store, { prevalidate: () => { throw new DeterministicProjectionErrorV2("bad hash", { failureCode: "hash_invalid", failureDetail: "bad hash" }); } });
    await expect(projector.projectCapturedBatch(batch())).resolves.toMatchObject({ status: "quarantined" });
    expect([store.events.size, store.cursors.size, store.batches.size, store.quarantines]).toEqual([0, 0, 0, ["hash_invalid"]]);
  });
});
