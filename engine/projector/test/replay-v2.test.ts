import { afterEach, describe, expect, test } from "bun:test";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

import { RunEventEmitterV2 } from "../src/emitter";
import type { EventEnvelopeDraftV2 } from "../src/event-contract";
import { DurableTipClientV2 } from "../src/durable-tip-client-v2";
import { projectionBatchIdV2 } from "../src/projection-batch-v2";
import { prevalidateReplayV2, V2PrevalidationError } from "../src/prevalidate-v2";
import { ReplayVerificationError, verifyReplayV2 } from "../src/replay-verifier-v2";

const helperPath = resolve(import.meta.dir, "../../../shared/event_log_append_v2.py");
const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((directory) => rm(directory, { recursive: true, force: true })));
});

function draft(eventId: string): EventEnvelopeDraftV2 {
  return {
    schema_version: 2,
    event_id: eventId,
    idempotency_key: `key-${eventId}`,
    run_id: "run-v2",
    type: "reviewer.initial_review.task_started",
    occurred_at: "2026-07-12T10:00:00Z",
    actor: { agent_id: "reviewer-r2", role: "reviewer", phase: "initial_review" },
    payload: { task_id: eventId },
  };
}

async function setup() {
  const directory = await mkdtemp(join(tmpdir(), "ralphthon-replay-v2-"));
  temporaryDirectories.push(directory);
  const eventLogPath = join(directory, "events.ndjson");
  const emitter = new RunEventEmitterV2({ runId: "run-v2", eventLogPath, helperPath });
  return { eventLogPath, emitter };
}

describe("v2 proof-oriented replay", () => {
  test("uses the captured durable tip and refuses a later visible LF record", async () => {
    const { eventLogPath, emitter } = await setup();
    const first = await emitter.emit(draft("evt-1"));
    await emitter.emit(draft("evt-2"));

    const replay = await verifyReplayV2(eventLogPath, "run-v2", first.durable_tip);
    expect(replay.records.map((record) => record.raw.event_id)).toEqual(["evt-1"]);
    expect(replay.records.at(-1)?.endOffset).toBe(first.durable_tip.end_offset);
  });

  test("retains only a bounded verified suffix while preserving the captured tip", async () => {
    const { eventLogPath, emitter } = await setup();
    await emitter.emit(draft("evt-1"));
    await emitter.emit(draft("evt-2"));
    const tip = (await emitter.emit(draft("evt-3"))).durable_tip;

    const first = await verifyReplayV2(eventLogPath, "run-v2", tip, undefined, { maxRecords: 2, maxBytes: 1_048_576 });
    expect(first.records.map((record) => record.raw.event_id)).toEqual(["evt-1", "evt-2"]);

    const last = first.records.at(-1)!;
    const second = await verifyReplayV2(eventLogPath, "run-v2", tip, {
      byteOffset: last.endOffset,
      lastSequence: last.raw.sequence,
      lastEventId: last.raw.event_id,
      lastEventHash: last.raw.event_hash,
    }, { maxRecords: 2, maxBytes: 1_048_576 });
    expect(second.records.map((record) => record.raw.event_id)).toEqual(["evt-3"]);
  });

  test("rejects a cursor that does not anchor the verified event", async () => {
    const { eventLogPath, emitter } = await setup();
    const result = await emitter.emit(draft("evt-1"));

    await expect(verifyReplayV2(eventLogPath, "run-v2", result.durable_tip, {
      byteOffset: result.durable_tip.end_offset,
      lastSequence: 1,
      lastEventId: "other-event",
      lastEventHash: result.durable_tip.last_event_hash,
    })).rejects.toBeInstanceOf(ReplayVerificationError);
  });

  test("rejects a corrupted canonical hash chain", async () => {
    const { eventLogPath, emitter } = await setup();
    const result = await emitter.emit(draft("evt-1"));
    const line = await readFile(eventLogPath, "utf8");
    await writeFile(eventLogPath, line.replace("evt-1", "evt-x"), "utf8");

    await expect(verifyReplayV2(eventLogPath, "run-v2", result.durable_tip)).rejects.toBeInstanceOf(ReplayVerificationError);
  });

  test("rejects unknown v2 event types before any projection transaction", async () => {
    const { eventLogPath, emitter } = await setup();
    const result = await emitter.emit(draft("evt-1"));
    const replay = await verifyReplayV2(eventLogPath, "run-v2", result.durable_tip);

    expect(() => prevalidateReplayV2(replay, new Set<string>())).toThrow(V2PrevalidationError);
  });

  test("derives deterministic batch identities", async () => {
    const { eventLogPath, emitter } = await setup();
    const result = await emitter.emit(draft("evt-1"));
    const replay = await verifyReplayV2(eventLogPath, "run-v2", result.durable_tip);
    const cursor = { byteOffset: 0, lastSequence: 0 };

    const first = projectionBatchIdV2("run-v2", eventLogPath, result.durable_tip, cursor, replay.records.map(({ event }) => event));
    const second = projectionBatchIdV2("run-v2", eventLogPath, result.durable_tip, cursor, replay.records.map(({ event }) => event));
    expect(first).toBe(second);
  });

  test("captures a tip only through the authority capture command", async () => {
    const captured = {
      schema_version: 2 as const,
      log_dev: 1,
      log_ino: 2,
      end_offset: 0,
      last_sequence: 0,
      last_event_hash: `sha256:${"0".repeat(64)}`,
    };
    const calls: Array<{ file: string; args: readonly string[] }> = [];
    const client = new DurableTipClientV2({
      helperPath: "authority.py",
      pythonExecutable: "python-test",
      runner: async (file, args) => {
        calls.push({ file, args });
        return { stdout: JSON.stringify(captured), stderr: "" };
      },
    });

    await expect(client.capture("events.ndjson", "run-v2")).resolves.toEqual(captured);
    expect(calls).toEqual([{
      file: "python-test",
      args: ["authority.py", "capture", "events.ndjson", "run-v2"],
    }]);
  });
});
