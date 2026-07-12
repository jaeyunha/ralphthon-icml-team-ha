import { describe, expect, test } from "bun:test";
import { canonicalJson, sha256Bytes } from "@ralph-review/contracts";


import {
  PostgresProjectionStoreV2,
  ProjectionStorageConflictErrorV2,
  type PgClient,
  type PgPool,
  type PgQueryResult,
  type PgQueryable,
  type ProjectionBatchV2,
} from "../src";

const hash = (value: string) => `sha256:${value.padEnd(64, "0")}`;

function result<TRow extends object>(rows: TRow[] = [], rowCount = rows.length): PgQueryResult<TRow> {
  return { rows, rowCount };
}

function batch(): ProjectionBatchV2 {
  const eventHash = hash("b");
  return {
    batchId: "batch-2",
    runId: "run-v2",
    source: "events.ndjson",
    durableTip: { schema_version: 2, log_dev: 1, log_ino: 2, end_offset: 200, last_sequence: 2, last_event_hash: eventHash },
    cursorAnchor: { byteOffset: 100, lastSequence: 1, lastEventId: "event-1", lastEventHash: hash("a") },
    events: [{
      byteOffset: 100,
      envelope: {
        schema_version: 2, event_id: "event-2", idempotency_key: "key-2", run_id: "run-v2", sequence: 2,
        previous_event_hash: hash("a"), event_hash: eventHash, type: "reviewer.initial_review.task_started",
        occurred_at: "2026-07-12T00:00:01Z",
        actor: { agent_id: "reviewer", role: "reviewer", phase: "initial_review" }, payload: { task_id: "event-2" },
      },
      event: {
        id: "event-2", runId: "run-v2", sequence: 2, type: "reviewer.initial_review.task_started",
        occurredAt: "2026-07-12T00:00:01Z", agentId: "reviewer", actorRole: "reviewer",
        phase: "initial_review", payload: { task_id: "event-2" },
      },
    }],
    nextCursor: {
      runId: "run-v2", source: "events.ndjson", byteOffset: 200, lastSequence: 2,
      lastEventId: "event-2", lastEventHash: eventHash, lastEndOffset: 200,
      verifiedFromGenesisAt: "2026-07-12T00:00:01Z", updatedAt: "2026-07-12T00:00:01Z",
    },
  };
}

function verifiedCursorRow() {
  return {
    run_id: "run-v2", source: "events.ndjson", byte_offset: 100, last_sequence: 1,
    last_event_id: "event-1", last_event_hash: hash("a"), last_end_offset: 100,
    verified_from_genesis_at: "2026-07-12T00:00:00Z", updated_at: "2026-07-12T00:00:00Z",
  };
}

class FakePool implements PgPool {
  constructor(private readonly currentCursor: object | undefined) {}

  async query<TRow extends object = Record<string, unknown>>(): Promise<PgQueryResult<TRow>> {
    return result<TRow>();
  }

  async connect(): Promise<PgClient> {
    const currentCursor = this.currentCursor;
    const client: PgClient = {
      async query<TRow extends object = Record<string, unknown>>(text: string): Promise<PgQueryResult<TRow>> {
        if (text.includes("FROM projection_cursors") && text.includes("FOR UPDATE")) {
          return result(currentCursor === undefined ? [] : [currentCursor as TRow]);
        }
        if (text.includes("INSERT INTO events")) return result<TRow>([], 1);
        return result<TRow>();
      },
      release() {},
    };
    return client;
  }
}

describe("PostgresProjectionStoreV2 cursor authority", () => {
  test("rejects an offset-only cursor instead of reporting caught-up from an unverifiable position", async () => {
    const pool: PgPool = {
      async query<TRow extends object = Record<string, unknown>>(): Promise<PgQueryResult<TRow>> {
        return result([{
          ...verifiedCursorRow(), last_event_id: null, last_event_hash: null,
        } as TRow]);
      },
      async connect() { throw new Error("not used"); },
    };
    const store = new PostgresProjectionStoreV2(pool, async (_client: PgQueryable) => {});

    await expect(store.loadCursorV2("run-v2", "events.ndjson")).rejects.toBeInstanceOf(ProjectionStorageConflictErrorV2);
  });

  test("does not permit a locked batch to overwrite its verified cursor with a stale position", async () => {
    const store = new PostgresProjectionStoreV2(new FakePool(verifiedCursorRow()), async () => {});
    const captured = batch();

    await expect(store.transactionV2("run-v2", async (tx) => {
      await tx.persistCanonicalEnvelope(captured.events[0]!, captured);
      await tx.saveCursorV2({ ...captured.nextCursor, byteOffset: captured.cursorAnchor.byteOffset, lastEndOffset: captured.cursorAnchor.byteOffset });
    })).rejects.toBeInstanceOf(ProjectionStorageConflictErrorV2);
  });

  test("treats a canonical-envelope difference as a conflict even when every identity key matches", async () => {
    const captured = batch();
    const persistedEnvelope = {
      ...captured.events[0]!.envelope,
      payload: { task_id: "different-task" },
    };
    const pool: PgPool = {
      async query<TRow extends object = Record<string, unknown>>(): Promise<PgQueryResult<TRow>> {
        return result<TRow>();
      },
      async connect(): Promise<PgClient> {
        return {
          async query<TRow extends object = Record<string, unknown>>(text: string): Promise<PgQueryResult<TRow>> {
            if (text.includes("FROM projection_cursors") && text.includes("FOR UPDATE")) {
              return result([verifiedCursorRow() as TRow]);
            }
            if (text.includes("INSERT INTO events")) return result<TRow>([], 0);
            if (text.includes("canonical_envelope_hash FROM events")) {
              const event = captured.events[0]!.envelope;
              return result([{
                id: event.event_id, run_id: event.run_id, sequence: event.sequence,
                idempotency_key: event.idempotency_key, previous_event_hash: event.previous_event_hash,
                event_hash: event.event_hash, canonical_envelope: persistedEnvelope,
                canonical_envelope_hash: sha256Bytes(canonicalJson(event)),
              } as TRow]);
            }
            return result<TRow>();
          },
          release() {},
        };
      },
    };
    const store = new PostgresProjectionStoreV2(pool, async () => {});

    await store.transactionV2("run-v2", async (tx) => {
      await expect(tx.persistCanonicalEnvelope(captured.events[0]!, captured)).resolves.toEqual({ status: "conflict" });
    });
  });
});
