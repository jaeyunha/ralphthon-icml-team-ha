import { afterEach, describe, expect, test } from "bun:test";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

import {
  EventAppendV2Error,
  RunEventEmitterV2,
  readNdjsonBatchV2,
  type EventEnvelopeDraftV2,
} from "../src";

const temporaryDirectories: string[] = [];
const helperPath = resolve(import.meta.dir, "../../../shared/event_log_append_v2.py");

afterEach(async () => {
  await Promise.all(
    temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true, force: true })),
  );
});

async function temporaryDirectory(): Promise<string> {
  const directory = await mkdtemp(join(tmpdir(), "ralphthon-event-v2-"));
  temporaryDirectories.push(directory);
  return directory;
}

function draft(eventId: string, payload: Record<string, string> = { task_id: eventId }): EventEnvelopeDraftV2 {
  return {
    schema_version: 2,
    event_id: eventId,
    idempotency_key: `key-${eventId}`,
    run_id: "run-v2",
    type: "reviewer.initial_review.task_started",
    occurred_at: "2026-07-12T10:00:00Z",
    actor: { agent_id: "reviewer-r2", role: "reviewer", phase: "initial_review" },
    payload,
  };
}

async function emitter() {
  const directory = await temporaryDirectory();
  const eventLogPath = join(directory, "events-v2.ndjson");
  return {
    eventLogPath,
    emitter: new RunEventEmitterV2({ runId: "run-v2", eventLogPath, helperPath }),
  };
}

describe("v2 Python append bridge", () => {
  test("persists deterministic chronology-free drafts and delegates the append", async () => {
    const { emitter: v2, eventLogPath } = await emitter();
    const result = await v2.emit(draft("evt-v2-1"));

    expect(result.status).toBe("appended");
    expect(result.envelope).toMatchObject({
      schema_version: 2,
      sequence: 1,
      previous_event_hash: `sha256:${"0".repeat(64)}`,
    });
    expect(result.durable_tip.last_sequence).toBe(1);
    const persistedDraft = JSON.parse(
      await readFile(join(resolve(eventLogPath, ".."), ".event-v2-drafts", "evt-v2-1.json"), "utf8"),
    ) as Record<string, unknown>;
    expect(persistedDraft).not.toHaveProperty("sequence");
    expect(persistedDraft).not.toHaveProperty("previous_event_hash");
    expect(persistedDraft).not.toHaveProperty("event_hash");
  });

  test("reconciles exact retries as duplicates and rejects identity conflicts", async () => {
    const { emitter: v2 } = await emitter();
    const first = draft("evt-v2-1");
    await v2.emit(first);

    await expect(v2.emit(first)).resolves.toMatchObject({ status: "duplicate" });
    await expect(v2.emit(draft("evt-v2-1", { task_id: "conflict" }))).rejects.toBeInstanceOf(
      EventAppendV2Error,
    );
  });

  test("reads only through a captured durable tip", async () => {
    const { emitter: v2, eventLogPath } = await emitter();
    const first = await v2.emit(draft("evt-v2-1"));
    await v2.emit(draft("evt-v2-2"));

    const batch = await readNdjsonBatchV2(eventLogPath, 0, first.durable_tip);
    expect(batch.records.map(({ raw }) => raw.sequence)).toEqual([1]);
    expect(batch.fileSize).toBe(first.durable_tip.end_offset);
    expect(batch.hasIncompleteLine).toBeFalse();
  });
});
