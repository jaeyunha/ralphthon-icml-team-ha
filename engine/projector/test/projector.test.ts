import { EventSequenceAllocator } from "@ralph-review/contracts";
import type { EventEnvelope } from "@ralph-review/schemas";
import { afterEach, describe, expect, test } from "bun:test";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

import {
  EventContractError,
  EventSequenceError,
  NdjsonProjector,
  RunEventEmitter,
  appendAllocatedEvent,
  appendEvent,
  readNdjsonBatch,
  w0EventAdapter,
  createPostgresJsPool,
  w0EventDraftAdapter,
  type EventEnvelopeDraft,
  type ProjectionCursor,
  type ProjectionStore,
  type ProjectionTransaction,
  type ProjectorEvent,
  type PostgresJsSql,
} from "../src";

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(
    temporaryDirectories.splice(0).map((path) =>
      rm(path, { recursive: true, force: true }),
    ),
  );
});

async function temporaryDirectory() {
  const directory = await mkdtemp(join(tmpdir(), "ralphthon-projector-"));
  temporaryDirectories.push(directory);
  return directory;
}

async function eventLog(name = "events.ndjson") {
  return join(await temporaryDirectory(), name);
}

function rawEvent(
  sequence: number,
  overrides: Partial<EventEnvelope> = {},
): EventEnvelope {
  return {
    event_id: `evt-${sequence}`,
    run_id: "run-1",
    sequence,
    type: "reviewer.initial_review.task_started",
    occurred_at: `2026-07-01T10:00:${String(sequence).padStart(2, "0")}Z`,
    actor: {
      agent_id: "reviewer-r2",
      role: "reviewer",
      phase: "initial_review",
    },
    payload: { task_id: `task-${sequence}` },
    ...overrides,
  };
}

function eventDraft(eventId: string): EventEnvelopeDraft {
  return {
    event_id: eventId,
    run_id: "run-1",
    type: "reviewer.initial_review.task_started",
    occurred_at: "2026-07-01T10:00:00Z",
    actor: {
      agent_id: "reviewer-r2",
      role: "reviewer",
      phase: "initial_review",
    },
    payload: { task_id: eventId },
  };
}

class MemoryStore implements ProjectionStore {
  events = new Map<string, ProjectorEvent>();
  sequences = new Map<string, string>();
  cursors = new Map<string, ProjectionCursor>();
  projections: string[] = [];
  notifications: string[] = [];
  order: string[] = [];
  failProjectionAt: number | undefined;

  cursorKey(runId: string, source: string) {
    return `${runId}\u0000${source}`;
  }

  async loadCursor(runId: string, source: string) {
    return this.cursors.get(this.cursorKey(runId, source));
  }

  async transaction<T>(work: (tx: ProjectionTransaction) => Promise<T>): Promise<T> {
    this.order.push("begin");
    const events = new Map(this.events);
    const sequences = new Map(this.sequences);
    const cursors = new Map(this.cursors);
    const projections = [...this.projections];
    const tx: ProjectionTransaction = {
      insertEvent: async (event) => {
        const sequenceKey = `${event.runId}:${event.sequence}`;
        const existingId = sequences.get(sequenceKey);
        const existing = this.events.get(event.id);
        if (existingId !== undefined || existing !== undefined) {
          if (existingId !== event.id || existing?.sequence !== event.sequence) {
            throw new Error("event identity conflict");
          }
          return { status: "duplicate" } as const;
        }
        events.set(event.id, event);
        sequences.set(sequenceKey, event.id);
        return { status: "inserted" } as const;
      },
      applyReadModels: async (event) => {
        if (event.sequence === this.failProjectionAt) throw new Error("injected crash");
        projections.push(event.id);
      },
      saveCursor: async (cursor) => {
        cursors.set(this.cursorKey(cursor.runId, cursor.source), cursor);
      },
    };

    try {
      const result = await work(tx);
      this.events = events;
      this.sequences = sequences;
      this.cursors = cursors;
      this.projections = projections;
      this.order.push("commit");
      return result;
    } catch (error) {
      this.order.push("rollback");
      throw error;
    }
  }

  async notifyCommitted(event: ProjectorEvent) {
    this.order.push(`notify:${event.id}`);
    this.notifications.push(event.id);
  }
}

describe("frozen W0 event contract", () => {
  test("accepts W0's sample-run event envelope without aliases", async () => {
    const fixture = JSON.parse(
      await readFile(
        resolve(import.meta.dir, "../../../tests/fixtures/contracts/sample-run/event-envelope.json"),
        "utf8",
      ),
    ) as EventEnvelope;

    expect(w0EventAdapter.normalize(fixture)).toMatchObject({
      id: "evt-fixture-001",
      runId: "run-fixture-001",
      sequence: 1,
      actorRole: "reviewer",
      phase: "initial_review",
      agentId: "reviewer-r2",
    });
  });

  test("rejects schema-valid-looking events whose actor disagrees with the type", () => {
    const invalid = rawEvent(1, {
      actor: { agent_id: "reviewer-r2", role: "author", phase: "initial_review" },
    });
    expect(() => w0EventAdapter.normalize(invalid)).toThrow(EventContractError);
  });
});

describe("NDJSON event log", () => {
  test("uses W0 allocation and serializes concurrent append order", async () => {
    const directory = await temporaryDirectory();
    const path = join(directory, "events.ndjson");
    const emitter = new RunEventEmitter({
      runId: "run-1",
      eventLogPath: path,
      sequenceStatePath: join(directory, "event-sequence.json"),
    });

    await Promise.all(
      Array.from({ length: 8 }, (_, index) => emitter.emit(eventDraft(`evt-${index + 1}`))),
    );

    const batch = await readNdjsonBatch(path, 0, w0EventAdapter);
    expect(batch.records.map(({ event }) => event.sequence)).toEqual([
      1, 2, 3, 4, 5, 6, 7, 8,
    ]);
    expect(new Set(batch.records.map(({ event }) => event.id).values()).size).toBe(8);
    expect(batch.nextOffset).toBe(batch.fileSize);
    expect(batch.hasIncompleteLine).toBeFalse();
  });

  test("accepts the frozen allocator directly", async () => {
    const directory = await temporaryDirectory();
    const path = join(directory, "events.ndjson");
    const allocator = new EventSequenceAllocator(
      join(directory, "event-sequence.json"),
      "run-1",
    );

    await appendAllocatedEvent(
      path,
      "run-1",
      eventDraft("evt-1") as EventEnvelopeDraft & { sequence?: number },
      allocator,
      w0EventDraftAdapter,
    );

    const batch = await readNdjsonBatch(path, 0, w0EventAdapter);
    expect(batch.records[0]?.event.sequence).toBe(1);
  });

  test("rejects producer sequence gaps and waits for an incomplete trailing line", async () => {
    const path = await eventLog();
    await appendEvent(path, rawEvent(1), w0EventAdapter);
    await expect(appendEvent(path, rawEvent(3), w0EventAdapter)).rejects.toThrow(
      "expected 2, received 3",
    );

    const complete = `${JSON.stringify(rawEvent(1))}\n`;
    await writeFile(path, `${complete}${JSON.stringify(rawEvent(2))}`);
    const batch = await readNdjsonBatch(path, 0, w0EventAdapter);
    expect(batch.records).toHaveLength(1);
    expect(batch.hasIncompleteLine).toBeTrue();
    expect(batch.nextOffset).toBe(Buffer.byteLength(complete));
  });
});

describe("transactional projection", () => {
  test("double replay is idempotent and only newly inserted events notify", async () => {
    const path = await eventLog();
    await appendEvent(path, rawEvent(1), w0EventAdapter);
    await appendEvent(path, rawEvent(2), w0EventAdapter);
    const store = new MemoryStore();
    const projector = new NdjsonProjector(store, w0EventAdapter);

    const first = await projector.projectBatch("run-1", path);
    store.cursors.clear();
    const replay = await projector.projectBatch("run-1", path);

    expect(first).toMatchObject({ inserted: 2, duplicates: 0, notified: 2 });
    expect(replay).toMatchObject({ inserted: 0, duplicates: 2, notified: 0 });
    expect(store.events.size).toBe(2);
    expect(store.projections).toEqual(["evt-1", "evt-2"]);
    expect(store.notifications).toEqual(["evt-1", "evt-2"]);
  });

  test("rejects out-of-order input before opening a database transaction", async () => {
    const path = await eventLog();
    await writeFile(
      path,
      `${JSON.stringify(rawEvent(1))}\n${JSON.stringify(rawEvent(3))}\n`,
    );
    const store = new MemoryStore();
    const projector = new NdjsonProjector(store, w0EventAdapter);

    await expect(projector.projectBatch("run-1", path)).rejects.toBeInstanceOf(
      EventSequenceError,
    );
    expect(store.order).toEqual([]);
    expect(store.events.size).toBe(0);
  });

  test("crash mid-batch rolls back cursor and projections, then restart recovers", async () => {
    const path = await eventLog();
    await appendEvent(path, rawEvent(1), w0EventAdapter);
    await appendEvent(path, rawEvent(2), w0EventAdapter);
    await appendEvent(path, rawEvent(3), w0EventAdapter);
    const store = new MemoryStore();
    store.failProjectionAt = 2;
    const projector = new NdjsonProjector(store, w0EventAdapter);

    await expect(projector.projectBatch("run-1", path)).rejects.toThrow("injected crash");
    expect(store.events.size).toBe(0);
    expect(store.cursors.size).toBe(0);
    expect(store.projections).toEqual([]);
    expect(store.notifications).toEqual([]);

    store.failProjectionAt = undefined;
    const recovered = await projector.projectBatch("run-1", path);
    expect(recovered).toMatchObject({ inserted: 3, duplicates: 0, notified: 3 });
    expect(store.events.size).toBe(3);
    expect(store.projections).toEqual(["evt-1", "evt-2", "evt-3"]);
    expect(store.cursors.values().next().value).toMatchObject({
      lastSequence: 3,
      lastEventId: "evt-3",
    });
  });

  test("notifications happen strictly after transaction commit", async () => {
    const path = await eventLog();
    await appendEvent(path, rawEvent(1), w0EventAdapter);
    const store = new MemoryStore();
    const projector = new NdjsonProjector(store, w0EventAdapter);

    await projector.projectBatch("run-1", path);
    expect(store.order).toEqual(["begin", "commit", "notify:evt-1"]);
  });
});

test("postgres-js adapter preserves typed JSON parameters", async () => {
  const calls: unknown[][] = [];
  const result = Object.assign([], { count: 0 });
  const unsafe = async (_query: string, parameters: readonly unknown[] = []) => {
    calls.push([...parameters]);
    return result;
  };
  const sql = {
    unsafe,
    async reserve() {
      return {
        unsafe,
        release() {},
      };
    },
  } as unknown as PostgresJsSql;
  const pool = createPostgresJsPool(sql);
  const date = new Date("2026-07-11T00:00:00Z");
  const bytes = new Uint8Array([1, 2, 3]);
  const payload = { nested: ["value"] };

  await pool.query("SELECT $1::jsonb, $2, $3, $4", [
    payload,
    date,
    bytes,
    null,
  ]);

  expect(calls).toEqual([[payload, date, bytes, null]]);
  const serializingPool = createPostgresJsPool(sql, {
    serializeJsonParameters: true,
  });
  await serializingPool.query("SELECT $1::jsonb", [payload]);
  expect(calls[1]).toEqual(['{"nested":["value"]}']);
});
